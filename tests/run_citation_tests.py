import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import build_citation_key, extract_citations, parse_citation

TESTS_DIR = Path(__file__).resolve().parent
CASES_PATH = TESTS_DIR / "datasets" / "matching" / "citation_cases.json"
REPORT_PATH = TESTS_DIR / "citation_test_report.md"


def _normalize_keys(values) -> list[str]:
    if not isinstance(values, list):
        return []
    keys = [str(value).strip() for value in values if str(value).strip()]
    return sorted(set(keys))


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _run_case(case: dict) -> dict:
    case_id = str(case.get("id", ""))
    name = str(case.get("name", ""))
    text = str(case.get("text", ""))
    expected_keys = _normalize_keys(case.get("expected_keys"))

    try:
        extracted = extract_citations(text)
        extracted_raw = [str(item.get("raw", "")) for item in extracted if str(item.get("raw", "")).strip()]
        parsed_keys = []
        for citation in extracted:
            parsed_citation = parse_citation(citation)
            key = build_citation_key(parsed_citation)
            if key:
                parsed_keys.append(key)
        actual_keys = sorted(set(parsed_keys))
    except Exception as e:
        return {
            "id": case_id,
            "name": name,
            "passed": False,
            "reason": f"exception: {e.__class__.__name__}: {e}",
            "expected_keys": expected_keys,
            "actual_keys": [],
            "extracted_citations": [],
            "text": text,
        }

    return {
        "id": case_id,
        "name": name,
        "passed": actual_keys == expected_keys,
        "reason": "" if actual_keys == expected_keys else "key_set_mismatch",
        "expected_keys": expected_keys,
        "actual_keys": actual_keys,
        "extracted_citations": extracted_raw,
        "text": text,
    }


def _write_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    failed = total - passed
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Citation Extraction/Parsing Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    failures = [result for result in results if not result["passed"]]
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for failure in failures:
            lines.append(f"### {failure['id']} {failure['name']}")
            lines.append("")
            lines.append(f"- text_preview: {_preview(failure['text'])}")
            lines.append(f"- extracted_citations: {failure['extracted_citations']}")
            lines.append(f"- expected_keys: {failure['expected_keys']}")
            lines.append(f"- actual_keys: {failure['actual_keys']}")
            lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        return

    try:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read citation cases JSON: {e}")
        return

    if not isinstance(cases, list):
        print("Invalid cases format: expected a JSON array")
        return

    results = []
    for case in cases:
        result = _run_case(case)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']} {result['name']}")

    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    failed = total - passed

    print("---")
    print(f"Total: {total}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    if failed:
        print("Failure details:")
        for result in results:
            if result["passed"]:
                continue
            print(f"- {result['id']} {result['name']}: expected={result['expected_keys']} actual={result['actual_keys']}")

    _write_report(results, REPORT_PATH)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
