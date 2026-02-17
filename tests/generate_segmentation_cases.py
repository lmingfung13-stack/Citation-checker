import json
import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = TESTS_DIR / "datasets"
RAW_DIR = DATASETS_DIR / "raw_pastes"
OUT_PATH = DATASETS_DIR / "segmentation_cases.json"
EXPECTED_MAP_PATH = RAW_DIR / "expected_map.json"

SPECIAL_YEAR_TOKEN = r"(?:n\.?\s*d\.?|no\s*date|in\s*press|\u5370\u5237\u4e2d|\u672a\u520a)"
NUMERIC_YEAR_TOKEN = r"(?:19|20)\d{2}[a-z]?"
YEAR_TOKEN_PATTERN = re.compile(
    rf"\(\s*(?:{NUMERIC_YEAR_TOKEN}|{SPECIAL_YEAR_TOKEN})\s*\)|\b(?:{NUMERIC_YEAR_TOKEN}|{SPECIAL_YEAR_TOKEN})\b",
    re.IGNORECASE,
)
INLINE_YEAR_SPLIT_PATTERN = re.compile(
    rf"(?<=\.)\s+(?=[A-Za-z\u4e00-\u9fff][^()\n]{{0,90}}\(\s*(?:{NUMERIC_YEAR_TOKEN}|{SPECIAL_YEAR_TOKEN})\s*\))",
    re.IGNORECASE,
)


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def load_expected_map() -> dict[str, list[str]]:
    if not EXPECTED_MAP_PATH.exists():
        print(f"Expected map not found: {EXPECTED_MAP_PATH}")
        return {}

    try:
        data = json.loads(EXPECTED_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read expected map: {e}")
        return {}

    version = data.get("version")
    if version != 1:
        print(f"Warning: expected_map version is {version}, expected 1")

    raw_map = data.get("expected_items_by_file", {})
    if not isinstance(raw_map, dict):
        print("Warning: expected_items_by_file must be an object")
        return {}

    cleaned_map: dict[str, list[str]] = {}
    for filename, items in raw_map.items():
        if not isinstance(filename, str):
            continue
        if not isinstance(items, list):
            print(f"Warning: expected_items for {filename} is not a list; skipped")
            continue

        cleaned_items = []
        for item in items:
            text = str(item).strip()
            if text:
                cleaned_items.append(text)
        cleaned_map[filename] = cleaned_items

    return cleaned_map


def _trim_items(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


def _split_by_blank_lines_raw(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n+", text.strip())
    return _trim_items(blocks)


def _split_by_blank_lines(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n+", text.strip())
    items = []
    for block in blocks:
        lines = [re.sub(r"\s+", " ", line.strip()) for line in block.split("\n") if line.strip()]
        if lines:
            items.append(" ".join(lines))
    return items


def _split_by_year_fallback(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line.strip()) for line in text.split("\n") if line.strip()]
    if not lines:
        return []

    expanded = []
    for line in lines:
        parts = [p.strip() for p in INLINE_YEAR_SPLIT_PATTERN.split(line) if p.strip()]
        expanded.extend(parts if parts else [line])

    if not any(YEAR_TOKEN_PATTERN.search(line) for line in expanded):
        return [" ".join(expanded)]

    items = []
    current = []
    for seg in expanded:
        seg_has_year = YEAR_TOKEN_PATTERN.search(seg) is not None
        if current and seg_has_year:
            items.append(" ".join(current))
            current = [seg]
        else:
            current.append(seg)
    if current:
        items.append(" ".join(current))
    return items


def _split_by_year_fallback_raw(text: str) -> list[str]:
    normalized = _normalize_newlines(text).strip()
    if not normalized:
        return []

    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        return []

    expanded = []
    for line in lines:
        parts = [p.strip() for p in INLINE_YEAR_SPLIT_PATTERN.split(line) if p.strip()]
        expanded.extend(parts if parts else [line])

    if not any(YEAR_TOKEN_PATTERN.search(line) for line in expanded):
        return [" ".join(expanded).strip()]

    items = []
    current = []
    for seg in expanded:
        seg_has_year = YEAR_TOKEN_PATTERN.search(seg) is not None
        if current and seg_has_year:
            items.append(" ".join(current).strip())
            current = [seg]
        else:
            current.append(seg)
    if current:
        items.append(" ".join(current).strip())
    return _trim_items(items)


def build_expected_items(raw_text: str) -> list[str]:
    text = _normalize_newlines(raw_text).strip()
    if not text:
        return []
    if re.search(r"\n\s*\n", text):
        return _split_by_blank_lines_raw(text)
    return _split_by_year_fallback_raw(text)


def infer_expected_count(raw_text: str) -> int:
    return len(build_expected_items(raw_text))


def _find_split_idx(line: str) -> int | None:
    if len(line) < 28:
        return None
    mid = len(line) // 2
    candidates = []
    for i, ch in enumerate(line):
        if ch.isspace() and 5 <= i <= len(line) - 5:
            candidates.append(i)
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs(x - mid))


def mutate_insert_linebreaks(text: str) -> str:
    lines = _normalize_newlines(text).split("\n")
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        idx = _find_split_idx(line)
        if idx is None:
            out.append(line)
            continue
        out.append(line[:idx].rstrip())
        out.append(line[idx + 1 :].lstrip())
    return "\n".join(out)


def mutate_insert_spaces(text: str) -> str:
    lines = _normalize_newlines(text).split("\n")
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        mutated = re.sub(r",\s*", ",  ", line)
        mutated = mutated.replace(" ", "  ")
        mutated = mutated.replace("  ", "\t ", 1)
        out.append(mutated)
    return "\n".join(out)


def mutate_punctuation_full_half(text: str) -> str:
    half_to_full = {
        "(": "\uff08",
        ")": "\uff09",
        ",": "\uff0c",
        ".": "\u3002",
        ";": "\uff1b",
        "-": "\uff0d",
        "\u2013": "\uff0d",
        "\u2014": "\uff0d",
    }
    full_to_half = {
        "\uff08": "(",
        "\uff09": ")",
        "\uff0c": ",",
        "\u3002": ".",
        "\uff1b": ";",
        "\uff0d": "-",
    }
    out_chars = []
    for idx, ch in enumerate(_normalize_newlines(text)):
        if ch in half_to_full and idx % 2 == 0:
            out_chars.append(half_to_full[ch])
        elif ch in full_to_half and idx % 2 == 1:
            out_chars.append(full_to_half[ch])
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def _make_case(
    case_id: str,
    name: str,
    input_text: str,
    expected_count: int,
    notes: str,
    expected_items: list[str] | None = None,
) -> dict:
    return {
        "id": case_id,
        "name": name,
        "input": input_text,
        "expected_count": expected_count,
        "expected_items": expected_items,
        "notes": notes,
    }


def generate_cases() -> list[dict]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    txt_files = sorted(RAW_DIR.glob("*.txt"), key=lambda p: p.name.lower())
    if not txt_files:
        print(f"No input files found in: {RAW_DIR}")
        return []

    expected_map = load_expected_map()
    cases = []
    counter = 1
    skipped_missing_expected = []
    used_source_files = []

    for path in txt_files:
        raw_text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        if not raw_text.strip():
            print(f"Skip empty file: {path.name}")
            continue

        expected_items = expected_map.get(path.name)
        if expected_items is None:
            skipped_missing_expected.append(path.name)
            continue

        expected_count = len(expected_items)
        if expected_count <= 0:
            print(f"Skip invalid expected_count for file: {path.name}")
            continue

        variants = [
            ("base", raw_text, "base case from raw paste"),
            ("linebreak", mutate_insert_linebreaks(raw_text), "insert line breaks within item, no blank-line separator changes"),
            ("spaces", mutate_insert_spaces(raw_text), "insert extra spaces/tabs, preserve blank-line separators"),
            ("punct", mutate_punctuation_full_half(raw_text), "full/half punctuation replacement, preserve blank-line separators"),
        ]

        for suffix, case_input, note in variants:
            case_input = _normalize_newlines(case_input).rstrip("\n")
            if not case_input.strip():
                case_input = _normalize_newlines(raw_text).rstrip("\n")

            case_id = f"case{counter:03d}"
            case_name = f"{path.stem}_{suffix}"
            notes = f"source={path.name}; {note}; expected_count fixed to base"
            cases.append(
                _make_case(
                    case_id,
                    case_name,
                    case_input,
                    expected_count,
                    notes,
                    expected_items,
                )
            )
            counter += 1
        used_source_files.append(path.name)

    print(f"Used raw files with expected items: {len(used_source_files)}")
    if skipped_missing_expected:
        print(f"Skipped raw files without expected items: {len(skipped_missing_expected)}")
        for name in skipped_missing_expected:
            print(f"- {name}")
    else:
        print("Skipped raw files without expected items: 0")

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
    if not cases:
        print(f"Generated 0 cases. Output: {OUT_PATH}")
        return

    invalid = [
        c for c in cases
        if (not isinstance(c.get("expected_count"), int))
        or c["expected_count"] <= 0
        or (not str(c.get("input", "")).strip())
    ]
    if invalid:
        print(f"Warning: {len(invalid)} invalid cases detected.")

    source_files = len({c["name"].rsplit("_", 1)[0] for c in cases})
    print(f"Generated {len(cases)} cases from {source_files} raw files.")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
