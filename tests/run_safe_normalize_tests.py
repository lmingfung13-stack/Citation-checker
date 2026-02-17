import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import safe_normalize_reference_text

TESTS_DIR = Path(__file__).resolve().parent
CASES_PATH = TESTS_DIR / "datasets" / "safe_normalize_cases.json"
REPORT_PATH = TESTS_DIR / "safe_normalize_test_report.md"


def _preview(text: str, limit: int = 120) -> str:
    compact = (text or "").replace("\n", "\\n")
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _run_case(case: dict) -> dict:
    case_id = str(case.get("id", ""))
    name = str(case.get("name", ""))
    raw_input = str(case.get("input", ""))
    expected_output = str(case.get("expected_output", ""))

    try:
        actual_output = safe_normalize_reference_text(raw_input)
    except Exception as e:
        return {
            "id": case_id,
            "name": name,
            "passed": False,
            "reason": f"exception: {e.__class__.__name__}: {e}",
            "input": raw_input,
            "expected": expected_output,
            "actual": "",
        }

    return {
        "id": case_id,
        "name": name,
        "passed": actual_output == expected_output,
        "reason": "" if actual_output == expected_output else "normalized_output_mismatch",
        "input": raw_input,
        "expected": expected_output,
        "actual": actual_output,
    }


def _write_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Safe Normalize Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Pass rate: {pass_rate:.2f}%")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    failures = [r for r in results if not r["passed"]]
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for r in failures:
            lines.append(f"### {r['id']} {r['name']}")
            lines.append("")
            lines.append(f"- input_preview: `{_preview(r['input'])}`")
            lines.append("- expected:")
            lines.append("```text")
            lines.append(r["expected"])
            lines.append("```")
            lines.append("- actual:")
            lines.append("```text")
            lines.append(r["actual"])
            lines.append("```")
            lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        return

    try:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read cases JSON: {e}")
        return

    if not isinstance(cases, list):
        print("Invalid cases format: expected a JSON array")
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
            print(f"- {r['name']}: {r['reason']}")
            print(f"  expected={_preview(r['expected'])}")
            print(f"  actual={_preview(r['actual'])}")

    _write_report(results, REPORT_PATH)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
