import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import split_reference_items

TESTS_DIR = Path(__file__).resolve().parent
CASES_PATH = TESTS_DIR / "datasets" / "baseline_segmentation_cases.json"
REPORT_PATH = TESTS_DIR / "baseline_test_report.md"
EXPECTED_COUNT = 5


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _classify_count_mismatch(expected: int, actual: int) -> str:
    if actual < expected:
        return "merge_error"
    return "split_error"


def _run_case(case: dict) -> dict:
    name = str(case.get("name", "unknown"))
    raw_input = str(case.get("input", ""))
    expected_count = case.get("expected_count")

    if expected_count != EXPECTED_COUNT:
        return {
            "id": case.get("id", ""),
            "name": name,
            "passed": False,
            "failure_type": "exception",
            "reason": f"expected_count must be {EXPECTED_COUNT}",
            "expected_count": expected_count,
            "actual_count": 0,
            "items": [],
            "input": raw_input,
            "error": f"ValueError: expected_count must be {EXPECTED_COUNT}",
            "notes": str(case.get("notes", "")),
        }

    try:
        items = split_reference_items(raw_input)
    except Exception as e:
        return {
            "id": case.get("id", ""),
            "name": name,
            "passed": False,
            "failure_type": "exception",
            "reason": f"exception: {e.__class__.__name__}: {e}",
            "expected_count": expected_count,
            "actual_count": 0,
            "items": [],
            "input": raw_input,
            "error": f"{e.__class__.__name__}: {e}",
            "notes": str(case.get("notes", "")),
        }

    if any((item or "").strip() == "" for item in items):
        return {
            "id": case.get("id", ""),
            "name": name,
            "passed": False,
            "failure_type": "split_error",
            "reason": "empty_item_detected",
            "expected_count": expected_count,
            "actual_count": len(items),
            "items": items,
            "input": raw_input,
            "error": "",
            "notes": str(case.get("notes", "")),
        }

    actual_count = len(items)
    if actual_count != expected_count:
        return {
            "id": case.get("id", ""),
            "name": name,
            "passed": False,
            "failure_type": _classify_count_mismatch(expected_count, actual_count),
            "reason": f"expected_count={expected_count}, actual_count={actual_count}",
            "expected_count": expected_count,
            "actual_count": actual_count,
            "items": items,
            "input": raw_input,
            "error": "",
            "notes": str(case.get("notes", "")),
        }

    return {
        "id": case.get("id", ""),
        "name": name,
        "passed": True,
        "failure_type": "",
        "reason": "",
        "expected_count": expected_count,
        "actual_count": actual_count,
        "items": items,
        "input": raw_input,
        "error": "",
        "notes": str(case.get("notes", "")),
    }


def _write_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Baseline Segmentation Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Pass rate: {pass_rate:.2f}%")
    lines.append(f"- Expected count (fixed): {EXPECTED_COUNT}")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    failures = [r for r in results if not r["passed"]]
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for r in failures:
            lines.append(f"### {r['name']} ({r['failure_type']})")
            lines.append("")
            lines.append(f"- Expected: {r['expected_count']}")
            lines.append(f"- Actual: {r['actual_count']}")
            if r.get("error"):
                lines.append(f"- Error: {r['error']}")
            lines.append("- items_preview:")
            if r.get("items"):
                for idx, item in enumerate(r["items"], start=1):
                    lines.append(f"  {idx}. {_preview(item)}")
            else:
                lines.append("  1. (none)")
            lines.append(f"- notes: {r.get('notes', '')}")
            lines.append("")

    lines.append("## Passed Cases")
    lines.append("")
    for r in results:
        if r["passed"]:
            lines.append(f"- {r.get('id', '')} {r['name']}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        print("Please run: python tests/generate_baseline_segmentation_cases.py")
        return

    try:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read cases JSON: {e}")
        return

    if not isinstance(cases, list):
        print("Invalid cases format: expected a JSON array")
        return

    if not cases:
        print(f"No cases in {CASES_PATH}")
        _write_report([], REPORT_PATH)
        print(f"Report written: {REPORT_PATH}")
        return

    results = []
    for case in cases:
        result = _run_case(case)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['name']}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print("---")
    print(f"Total: {total}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")

    if failed:
        print("Failure details:")
        for r in results:
            if r["passed"]:
                continue
            print(f"- {r['name']} [{r['failure_type']}]: {r['reason']}")

    _write_report(results, REPORT_PATH)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
