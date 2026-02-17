import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import split_reference_items

TESTS_DIR = Path(__file__).resolve().parent
CASES_PATH = TESTS_DIR / "datasets" / "segmentation_cases.json"
REPORT_PATH = TESTS_DIR / "test_report.md"


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _classify_count_mismatch(expected: int, actual: int) -> str:
    if actual < expected:
        return "merge_error"
    return "split_error"


def _normalize_for_boundary(text: str) -> str:
    if text is None:
        return ""

    full_to_half = str.maketrans({
        "\uff08": "(",
        "\uff09": ")",
        "\uff0c": ",",
        "\u3002": ".",
        "\uff1b": ";",
        "\uff1a": ":",
        "\uff0d": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2010": "-",
        "\u3000": " ",
    })

    normalized = text.translate(full_to_half)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _compute_boundary_metrics(expected_items: list[str], predicted_items: list[str]) -> dict:
    normalized_expected = []
    for item in expected_items:
        normalized = _normalize_for_boundary(item)
        if normalized:
            normalized_expected.append(normalized)

    normalized_predicted = []
    for item in predicted_items:
        normalized = _normalize_for_boundary(item)
        if normalized:
            normalized_predicted.append(normalized)

    total_exp = len(normalized_expected)
    total_pred = len(normalized_predicted)

    if total_exp == 0 and total_pred == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if total_exp == 0:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    if total_pred == 0:
        return {"precision": 1.0, "recall": 0.0, "f1": 0.0}

    candidates = []
    for pred_idx, pred in enumerate(normalized_predicted):
        for exp_idx, exp in enumerate(normalized_expected):
            score = SequenceMatcher(None, pred, exp).ratio()
            candidates.append((score, pred_idx, exp_idx))
    candidates.sort(reverse=True)

    matched_pred = set()
    matched_exp = set()
    for score, pred_idx, exp_idx in candidates:
        if score < 0.85:
            break
        if pred_idx in matched_pred or exp_idx in matched_exp:
            continue
        matched_pred.add(pred_idx)
        matched_exp.add(exp_idx)

    matched_count = len(matched_pred)
    precision = matched_count / total_pred if total_pred else 0.0
    recall = matched_count / total_exp if total_exp else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _run_case(case: dict) -> dict:
    name = str(case.get("name", "unknown"))
    raw_input = str(case.get("input", ""))
    expected_count = case.get("expected_count")
    expected_items = case.get("expected_items")

    if not isinstance(expected_count, int):
        return {
            "id": case.get("id", ""),
            "name": name,
            "passed": False,
            "failure_type": "exception",
            "reason": "expected_count is not int",
            "expected_count": expected_count,
            "actual_count": 0,
            "items": [],
            "input": raw_input,
            "error": "ValueError: expected_count is not int",
            "notes": str(case.get("notes", "")),
            "metrics": None,
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
            "metrics": None,
        }

    metrics = None
    if isinstance(expected_items, list):
        metrics = _compute_boundary_metrics(expected_items, items)

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
            "metrics": metrics,
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
            "metrics": metrics,
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
        "metrics": metrics,
    }


def _write_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0

    metric_results = [r["metrics"] for r in results if isinstance(r.get("metrics"), dict)]
    avg_precision = sum(m["precision"] for m in metric_results) / len(metric_results) if metric_results else 0.0
    avg_recall = sum(m["recall"] for m in metric_results) / len(metric_results) if metric_results else 0.0
    avg_f1 = sum(m["f1"] for m in metric_results) / len(metric_results) if metric_results else 0.0
    no_blank_multi_results = [
        r for r in results
        if "no_blank_multi" in r.get("name", "").lower()
        or "no_blank_multi" in r.get("notes", "").lower()
    ]
    no_blank_multi_total = len(no_blank_multi_results)
    no_blank_multi_passed = sum(1 for r in no_blank_multi_results if r.get("passed"))

    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Segmentation Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Pass rate: {pass_rate:.2f}%")
    lines.append(f"- No-blank multi-ref cases: {no_blank_multi_passed} passed / {no_blank_multi_total} total")
    lines.append(f"- Avg item precision (cases with expected_items): {avg_precision:.4f}")
    lines.append(f"- Avg item recall (cases with expected_items): {avg_recall:.4f}")
    lines.append(f"- Avg item f1 (cases with expected_items): {avg_f1:.4f}")
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
            if isinstance(r.get("metrics"), dict):
                lines.append(
                    f"- Boundary metrics: "
                    f"precision={r['metrics']['precision']:.4f}, "
                    f"recall={r['metrics']['recall']:.4f}, "
                    f"f1={r['metrics']['f1']:.4f}"
                )
            if r.get("error"):
                lines.append(f"- Error: {r['error']}")
            lines.append("- items_preview:")
            if r.get("items"):
                for idx, item in enumerate(r["items"], start=1):
                    lines.append(f"  {idx}. {_preview(item)}")
            else:
                lines.append("  1. (none)")
            lines.append("")

    lines.append("## Low-F1 Cases")
    lines.append("")
    low_f1 = [r for r in results if isinstance(r.get("metrics"), dict) and r["metrics"]["f1"] < 0.8]
    low_f1.sort(key=lambda r: r["metrics"]["f1"])
    if not low_f1:
        lines.append("None")
        lines.append("")
    else:
        for r in low_f1[:10]:
            lines.append(
                f"- {r.get('id', '')} | {r['name']} | "
                f"precision={r['metrics']['precision']:.4f} | "
                f"recall={r['metrics']['recall']:.4f} | "
                f"f1={r['metrics']['f1']:.4f} | "
                f"notes={r.get('notes', '')}"
            )
        lines.append("")

    lines.append("## Case Metrics")
    lines.append("")
    for r in results:
        if isinstance(r.get("metrics"), dict):
            lines.append(
                f"- {r.get('id', '')} {r['name']}: "
                f"precision={r['metrics']['precision']:.4f}, "
                f"recall={r['metrics']['recall']:.4f}, "
                f"f1={r['metrics']['f1']:.4f}"
            )
        else:
            lines.append(f"- {r.get('id', '')} {r['name']}: precision=N/A, recall=N/A, f1=N/A")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        print("Please run: python tests/generate_segmentation_cases.py")
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
        print(f"No cases in {CASES_PATH}. Please run generator with dataset inputs.")
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
