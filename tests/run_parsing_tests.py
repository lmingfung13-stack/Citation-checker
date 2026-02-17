import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import parse_reference_item

TESTS_DIR = Path(__file__).resolve().parent
RAW_PASTES_DIR = TESTS_DIR / "datasets" / "raw_pastes"
EXPECTED_MAP_PATH = RAW_PASTES_DIR / "expected_map.json"
PARSING_EXPECTED_MAP_PATH = RAW_PASTES_DIR / "parsing_expected_map.json"
REPORT_PATH = TESTS_DIR / "parsing_test_report.md"
CHECK_FIELDS = ("first_author_surname", "year", "year_suffix", "year_token_type")


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _load_expected_items_map(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    raw_map = data.get("expected_items_by_file", {})
    if not isinstance(raw_map, dict):
        return {}

    cleaned: dict[str, list[str]] = {}
    for filename, items in raw_map.items():
        if not isinstance(filename, str) or not isinstance(items, list):
            continue
        cleaned[filename] = [str(item) for item in items]
    return cleaned


def _load_parsing_expected_map(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    raw_map = data.get("expected_parse_by_file", {})
    if not isinstance(raw_map, dict):
        return {}

    cleaned: dict[str, list[dict]] = {}
    for filename, items in raw_map.items():
        if not isinstance(filename, str) or not isinstance(items, list):
            continue
        cleaned_items = []
        for item in items:
            if isinstance(item, dict):
                cleaned_items.append(item)
        cleaned[filename] = cleaned_items
    return cleaned


def _write_report(results: list[dict], skipped_missing_expected: int, warnings: list[str], report_path: Path):
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = passed + failed + skipped_missing_expected
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Parsing Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Skipped missing expected: {skipped_missing_expected}")
    lines.append("")

    lines.append("## Warnings")
    lines.append("")
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    failures = [r for r in results if not r["passed"]]
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for failure in failures:
            lines.append(f"### {failure['file']} #{failure['index']}")
            lines.append("")
            lines.append(f"- item_preview: {_preview(failure['item'])}")
            lines.append("- expected:")
            lines.append("```json")
            lines.append(json.dumps(failure["expected"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- parsed:")
            lines.append("```json")
            lines.append(json.dumps(failure["parsed"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- diffs:")
            lines.append("```json")
            lines.append(json.dumps(failure["diffs"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    expected_items_by_file = _load_expected_items_map(EXPECTED_MAP_PATH)
    parsing_expected_by_file = _load_parsing_expected_map(PARSING_EXPECTED_MAP_PATH)

    raw_files = sorted(RAW_PASTES_DIR.glob("*.txt"), key=lambda p: p.name.lower())
    if not raw_files:
        print(f"No raw files found in {RAW_PASTES_DIR}")
        _write_report([], 0, [f"No raw files found in {RAW_PASTES_DIR}"], REPORT_PATH)
        print(f"Report written: {REPORT_PATH}")
        return

    results = []
    warnings = []
    skipped_missing_expected = 0

    for path in raw_files:
        filename = path.name
        expected_items = expected_items_by_file.get(filename)
        if expected_items is None:
            warnings.append(f"{filename}: missing expected_items in expected_map.json, skipped")
            continue

        expected_parse_list = parsing_expected_by_file.get(filename)
        if expected_parse_list is None:
            skipped_missing_expected += len(expected_items)
            warnings.append(f"{filename}: missing parsing expected map, skipped {len(expected_items)} item(s)")
            continue

        if not isinstance(expected_parse_list, list):
            skipped_missing_expected += len(expected_items)
            warnings.append(f"{filename}: parsing expected map is not a list, skipped {len(expected_items)} item(s)")
            continue

        for idx, item in enumerate(expected_items):
            if idx >= len(expected_parse_list):
                skipped_missing_expected += 1
                warnings.append(f"{filename}: missing parsing expected for item #{idx + 1}, skipped")
                continue

            expected = expected_parse_list[idx]
            parsed = parse_reference_item(item)

            diffs = {}
            for key in CHECK_FIELDS:
                if parsed.get(key) != expected.get(key):
                    diffs[key] = {"expected": expected.get(key), "parsed": parsed.get(key)}

            result = {
                "file": filename,
                "index": idx + 1,
                "item": item,
                "expected": {k: expected.get(k) for k in CHECK_FIELDS},
                "parsed": {k: parsed.get(k) for k in CHECK_FIELDS},
                "diffs": diffs,
                "passed": len(diffs) == 0,
            }
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(f"[{status}] {filename} #{idx + 1}")

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = passed + failed + skipped_missing_expected

    print("---")
    print(f"Total: {total}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    print(f"SKIP: {skipped_missing_expected}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    _write_report(results, skipped_missing_expected, warnings, REPORT_PATH)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
