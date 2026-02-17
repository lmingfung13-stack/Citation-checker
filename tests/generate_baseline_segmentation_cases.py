import json
import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = TESTS_DIR / "datasets"
BASELINE_PATH = DATASETS_DIR / "baseline" / "baseline_5refs.txt"
OUT_PATH = DATASETS_DIR / "baseline_segmentation_cases.json"


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _split_baseline_items(text: str) -> list[str]:
    normalized = _normalize_newlines(text).strip()
    if not normalized:
        return []
    blocks = re.split(r"\n\s*\n+", normalized)
    items = []
    for block in blocks:
        item = " ".join(line.strip() for line in block.split("\n") if line.strip())
        if item:
            items.append(item)
    return items


def _find_split_idx(item: str) -> int | None:
    if len(item) < 40:
        return None
    target = len(item) // 2
    candidates = [i for i, ch in enumerate(item) if ch == " " and 20 <= i <= len(item) - 20]
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs(x - target))


def _mutate_linebreak_item(item: str) -> str:
    idx = _find_split_idx(item)
    if idx is None:
        return item
    return item[:idx].rstrip() + "\n" + item[idx + 1 :].lstrip()


def _mutate_spaces_item(item: str) -> str:
    mutated = item.replace(", ", ",  ")
    mutated = mutated.replace(". ", ".  ")
    mutated = mutated.replace(" ", "  ", 1)
    return mutated


def _mutate_punct_text(text: str) -> str:
    half_to_full = {
        "(": "（",
        ")": "）",
        ",": "，",
        ".": "。",
        ";": "；",
        "-": "－",
        "–": "－",
        "—": "－",
    }
    full_to_half = {
        "（": "(",
        "）": ")",
        "，": ",",
        "。": ".",
        "；": ";",
        "－": "-",
    }

    out = []
    for idx, ch in enumerate(text):
        if ch in half_to_full and idx % 2 == 0:
            out.append(half_to_full[ch])
        elif ch in full_to_half and idx % 2 == 1:
            out.append(full_to_half[ch])
        else:
            out.append(ch)
    return "".join(out)


def _compose_base(items: list[str]) -> str:
    return "\n\n".join(items)


def _compose_no_blank(items: list[str]) -> str:
    return " ".join(items)


def _compose_linebreak(items: list[str]) -> str:
    return "\n\n".join(_mutate_linebreak_item(item) for item in items)


def _compose_spaces(items: list[str]) -> str:
    return "\n\n".join(_mutate_spaces_item(item) for item in items)


def _compose_punct(items: list[str]) -> str:
    return "\n\n".join(_mutate_punct_text(item) for item in items)


def _compose_mixed(items: list[str]) -> str:
    line_wrapped = [_mutate_linebreak_item(item) for item in items]
    no_blank_line_wrapped = "\n".join(line_wrapped)
    return _mutate_punct_text(no_blank_line_wrapped)


def _make_case(case_id: str, name: str, input_text: str, notes: str) -> dict:
    return {
        "id": case_id,
        "name": name,
        "input": _normalize_newlines(input_text).strip("\n"),
        "expected_count": 5,
        "notes": notes,
    }


def generate_cases() -> list[dict]:
    if not BASELINE_PATH.exists():
        print(f"Baseline file not found: {BASELINE_PATH}")
        return []

    raw_text = BASELINE_PATH.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    items = _split_baseline_items(raw_text)
    if len(items) != 5:
        print(f"Baseline item count is {len(items)} (expected 5).")

    variants = [
        ("base", _compose_base(items), "baseline original with blank-line separators"),
        ("no_blank", _compose_no_blank(items), "remove blank lines and concatenate all 5 references"),
        ("linebreak", _compose_linebreak(items), "insert deterministic in-item line wraps without crossing items"),
        ("spaces", _compose_spaces(items), "insert deterministic extra spaces/tabs within each item"),
        ("punct", _compose_punct(items), "apply deterministic full/half punctuation swaps and dash perturbation"),
        ("mixed", _compose_mixed(items), "combine no_blank + linebreak + punct mutations"),
    ]

    cases = []
    for idx, (suffix, input_text, note) in enumerate(variants, start=1):
        case_id = f"case{idx:03d}"
        case_name = f"baseline_5refs_{suffix}"
        notes = f"source={BASELINE_PATH.name}; {note}; expected_count fixed to 5"
        cases.append(_make_case(case_id, case_name, input_text, notes))
    return cases


def write_cases(cases: list[dict]):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    cases = generate_cases()
    write_cases(cases)
    print(f"Generated {len(cases)} baseline cases.")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
