import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import (
    build_citation_key,
    build_reference_key,
    extract_citations,
    match_citations,
    parse_citation,
    parse_reference_item,
)

TESTS_DIR = Path(__file__).resolve().parent
CASES_PATH = TESTS_DIR / "datasets" / "matching" / "matching_cases.json"
REPORT_PATH = TESTS_DIR / "matching_test_report.md"


def _normalize_key_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    keys = [str(v).strip() for v in values if str(v).strip()]
    return sorted(set(keys))


def _normalize_ambiguous_expected(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not key or not reason:
            continue
        try:
            count_min = int(item.get("candidate_count_min", 0))
        except Exception:
            count_min = 0
        normalized.append(
            {
                "key": key,
                "reason": reason,
                "candidate_count_min": max(0, count_min),
            }
        )
    return sorted(normalized, key=lambda x: (x["key"], x["reason"]))


def _normalize_ambiguous_actual(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not key or not reason:
            continue
        candidates = item.get("candidates", [])
        candidate_count = len(candidates) if isinstance(candidates, list) else 0
        normalized.append(
            {
                "key": key,
                "reason": reason,
                "candidate_count": candidate_count,
            }
        )
    return sorted(normalized, key=lambda x: (x["key"], x["reason"]))


def _compare_ambiguous(expected_items, actual_items) -> dict:
    expected_norm = _normalize_ambiguous_expected(expected_items)
    actual_norm = _normalize_ambiguous_actual(actual_items)

    expected_map = {(item["key"], item["reason"]): item["candidate_count_min"] for item in expected_norm}
    actual_map = {(item["key"], item["reason"]): item["candidate_count"] for item in actual_norm}

    missing_keys = sorted(set(expected_map.keys()) - set(actual_map.keys()))
    extra_keys = sorted(set(actual_map.keys()) - set(expected_map.keys()))

    count_violations = []
    for key in sorted(set(expected_map.keys()).intersection(set(actual_map.keys()))):
        if actual_map[key] < expected_map[key]:
            count_violations.append(
                {
                    "key": key[0],
                    "reason": key[1],
                    "expected_min": expected_map[key],
                    "actual_count": actual_map[key],
                }
            )

    if not missing_keys and not extra_keys and not count_violations:
        return {}

    return {
        "missing_keys": [{"key": key, "reason": reason} for key, reason in missing_keys],
        "extra_keys": [{"key": key, "reason": reason} for key, reason in extra_keys],
        "candidate_count_violations": count_violations,
    }


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _run_case(case: dict) -> dict:
    case_id = str(case.get("id", ""))
    name = str(case.get("name", ""))
    text = str(case.get("text", ""))
    references = case.get("references", [])
    expected = case.get("expected", {})

    if not isinstance(references, list):
        return {
            "id": case_id,
            "name": name,
            "passed": False,
            "reason": "references must be a list",
            "expected": expected,
            "actual": {},
            "parsed_ref_keys": [],
            "parsed_citation_keys": [],
            "extracted_citations": [],
        }

    refs = [str(item) for item in references]

    # debug keys (manual driver visibility)
    parsed_ref_keys = []
    for ref in refs:
        parsed_ref = parse_reference_item(ref)
        ref_key = build_reference_key(parsed_ref)
        if ref_key:
            parsed_ref_keys.append(ref_key)
    parsed_ref_keys = sorted(set(parsed_ref_keys))

    extracted = extract_citations(text)
    extracted_raw = [str(item.get("raw", "")) for item in extracted if str(item.get("raw", "")).strip()]

    parsed_citation_keys = []
    for citation in extracted:
        parsed_citation = parse_citation(citation)
        cite_key = build_citation_key(parsed_citation)
        if cite_key:
            parsed_citation_keys.append(cite_key)
    parsed_citation_keys = sorted(set(parsed_citation_keys))

    try:
        result = match_citations(text, refs)
    except Exception as e:
        return {
            "id": case_id,
            "name": name,
            "passed": False,
            "reason": f"exception: {e.__class__.__name__}: {e}",
            "expected": expected,
            "actual": {},
            "parsed_ref_keys": parsed_ref_keys,
            "parsed_citation_keys": parsed_citation_keys,
            "extracted_citations": extracted_raw,
        }

    expected_matched = _normalize_key_list(expected.get("matched"))
    expected_missing = _normalize_key_list(expected.get("missing_in_reference"))
    expected_extra = _normalize_key_list(expected.get("extra_in_reference"))
    expected_ambiguous = expected.get("ambiguous", [])

    actual_matched = _normalize_key_list(result.get("matched"))
    actual_missing = _normalize_key_list(result.get("missing_in_reference"))
    actual_extra = _normalize_key_list(result.get("extra_in_reference"))
    actual_ambiguous = result.get("ambiguous", [])

    diffs = {}
    if actual_matched != expected_matched:
        diffs["matched"] = {"expected": expected_matched, "actual": actual_matched}
    if actual_missing != expected_missing:
        diffs["missing_in_reference"] = {"expected": expected_missing, "actual": actual_missing}
    if actual_extra != expected_extra:
        diffs["extra_in_reference"] = {"expected": expected_extra, "actual": actual_extra}

    ambiguous_diff = _compare_ambiguous(expected_ambiguous, actual_ambiguous)
    if ambiguous_diff:
        diffs["ambiguous"] = ambiguous_diff

    return {
        "id": case_id,
        "name": name,
        "passed": len(diffs) == 0,
        "reason": "" if len(diffs) == 0 else "mismatch",
        "expected": {
            "matched": expected_matched,
            "missing_in_reference": expected_missing,
            "extra_in_reference": expected_extra,
            "ambiguous": _normalize_ambiguous_expected(expected_ambiguous),
        },
        "actual": {
            "matched": actual_matched,
            "missing_in_reference": actual_missing,
            "extra_in_reference": actual_extra,
            "ambiguous": _normalize_ambiguous_actual(actual_ambiguous),
        },
        "diffs": diffs,
        "parsed_ref_keys": parsed_ref_keys,
        "parsed_citation_keys": parsed_citation_keys,
        "extracted_citations": extracted_raw,
        "references": refs,
        "text": text,
    }


def _write_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    failed = total - passed
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Matching Test Report")
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
            lines.append(f"- parsed_citation_keys: {failure['parsed_citation_keys']}")
            lines.append(f"- parsed_ref_keys: {failure['parsed_ref_keys']}")
            lines.append(f"- extracted_citations: {failure['extracted_citations']}")
            lines.append("- expected:")
            lines.append("```json")
            lines.append(json.dumps(failure["expected"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- actual:")
            lines.append("```json")
            lines.append(json.dumps(failure["actual"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- diffs:")
            lines.append("```json")
            lines.append(json.dumps(failure["diffs"], ensure_ascii=False, indent=2))
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
        print(f"Failed to read matching cases JSON: {e}")
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
            print(f"- {result['id']} {result['name']}: {result['diffs']}")

    _write_report(results, REPORT_PATH)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
