import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from citation_core import read_docx_bytes, read_pdf_bytes
from services.reference_service import build_citation_key, extract_citations, match_citations, parse_citation

TESTS_DIR = Path(__file__).resolve().parent
DOCS_DIR = TESTS_DIR / "datasets" / "matching" / "docs"
CASES_PATH = TESTS_DIR / "datasets" / "matching" / "document_matching_cases.json"
REPORT_PATH = TESTS_DIR / "document_matching_test_report.md"
DEFAULT_HEADINGS = ["References", "REFERENCES", "Bibliography", "參考文獻", "参考文献"]
DEFAULT_MAX_CHARS = 120000


def _normalize_key_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    keys = [str(value).strip() for value in values if str(value).strip()]
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


def _preview(text: str, limit: int = 160) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _normalize_heading_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip()).lower()
    normalized = re.sub(r"[\s\.:：]+", "", normalized)
    return normalized


def _find_heading_char_index(full_text: str, headings: list[str]) -> tuple[int | None, bool]:
    lines = full_text.split("\n")
    cursor = 0
    target_headings = [_normalize_heading_text(h) for h in headings if str(h).strip()]

    for line in lines:
        line_norm = _normalize_heading_text(line)
        if line_norm:
            for heading_norm in target_headings:
                if not heading_norm:
                    continue
                if line_norm == heading_norm:
                    return cursor, True
                if line_norm.startswith(heading_norm) and len(line_norm) <= len(heading_norm) + 6:
                    return cursor, True
        cursor += len(line) + 1

    return None, False


def _resolve_max_chars(value, default_value: int = DEFAULT_MAX_CHARS) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default_value
    if parsed <= 0:
        return default_value
    return parsed


def _extract_with_mode(full_text: str, mode: str, headings: list[str], end_marker: str | None, max_chars: int) -> tuple[str | None, bool]:
    mode = (mode or "").strip().lower()

    if mode == "full_text":
        return full_text, False

    if mode == "first_n_chars":
        return full_text[:max_chars], False

    if mode == "until_marker":
        marker = (end_marker or "").strip()
        if not marker:
            return None, False
        idx = full_text.lower().find(marker.lower())
        if idx < 0:
            return None, False
        return full_text[:idx], False

    if mode == "before_heading":
        heading_idx, found = _find_heading_char_index(full_text, headings)
        if heading_idx is None:
            return None, False
        return full_text[:heading_idx], found

    return None, False


def _extract_body_text(full_text: str, body_extract: dict) -> dict:
    cfg = body_extract if isinstance(body_extract, dict) else {}

    mode = str(cfg.get("mode", "before_heading")).strip().lower() or "before_heading"
    fallback_mode = str(cfg.get("fallback_mode", "full_text")).strip().lower() or "full_text"
    max_chars = _resolve_max_chars(cfg.get("max_chars"), DEFAULT_MAX_CHARS)
    headings = cfg.get("headings") if isinstance(cfg.get("headings"), list) else DEFAULT_HEADINGS
    if not headings:
        headings = DEFAULT_HEADINGS
    end_marker = cfg.get("end_marker")

    body_text, heading_found = _extract_with_mode(full_text, mode, headings, end_marker, max_chars)
    used_mode = mode
    used_fallback = False

    if body_text is None:
        used_fallback = True
        if fallback_mode == mode:
            fallback_mode = "full_text"
        body_text, fallback_heading_found = _extract_with_mode(full_text, fallback_mode, headings, end_marker, max_chars)
        used_mode = fallback_mode
        heading_found = heading_found or fallback_heading_found

    if body_text is None:
        used_fallback = True
        used_mode = "full_text"
        body_text = full_text

    body_text = body_text[:max_chars]

    return {
        "body_text": body_text,
        "used_mode": used_mode,
        "used_fallback": used_fallback,
        "reference_heading_found": bool(heading_found),
    }


def _load_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    file_bytes = path.read_bytes()

    if suffix == ".pdf":
        paragraphs = read_pdf_bytes(file_bytes)
    elif suffix == ".docx":
        paragraphs = read_docx_bytes(file_bytes)
    else:
        raise ValueError(f"Unsupported file extension: {suffix}")

    return "\n".join((p.text or "") for p in paragraphs if str(p.text or "").strip())


def _validate_matching_expected(expected_matching: dict, citation_keys: list[str]) -> list[str]:
    if not isinstance(expected_matching, dict):
        return ["expected.matching must be an object"]

    matched = set(_normalize_key_list(expected_matching.get("matched")))
    missing = set(_normalize_key_list(expected_matching.get("missing_in_reference")))
    extra = set(_normalize_key_list(expected_matching.get("extra_in_reference")))
    ambiguous_items = _normalize_ambiguous_expected(expected_matching.get("ambiguous", []))
    ambiguous_keys = {item["key"] for item in ambiguous_items}

    violations = []

    overlap_1 = sorted(matched.intersection(missing))
    overlap_2 = sorted(matched.intersection(ambiguous_keys))
    overlap_3 = sorted(missing.intersection(ambiguous_keys))
    if overlap_1 or overlap_2 or overlap_3:
        violations.append(
            "rule1_overlap_in_matched_missing_ambiguous: "
            + json.dumps(
                {
                    "matched_and_missing": overlap_1,
                    "matched_and_ambiguous": overlap_2,
                    "missing_and_ambiguous": overlap_3,
                },
                ensure_ascii=False,
            )
        )

    citation_set = set(_normalize_key_list(citation_keys))
    required = matched.union(missing).union(ambiguous_keys)
    missing_from_citation_keys = sorted(required.difference(citation_set))
    if missing_from_citation_keys:
        violations.append(
            "rule2_citation_keys_not_covering_matched_missing_ambiguous: "
            + json.dumps(missing_from_citation_keys, ensure_ascii=False)
        )

    overlap_extra_matched = sorted(extra.intersection(matched))
    if overlap_extra_matched:
        violations.append(
            "rule3_extra_overlaps_matched: " + json.dumps(overlap_extra_matched, ensure_ascii=False)
        )

    return violations


def _run_case(case: dict) -> dict:
    case_id = str(case.get("id", "")).strip()
    case_name = str(case.get("name", "")).strip()
    file_name = str(case.get("file", "")).strip()
    expected = case.get("expected", {}) if isinstance(case.get("expected", {}), dict) else {}

    base_result = {
        "id": case_id,
        "name": case_name,
        "file": file_name,
        "status": "failed",
        "reason": "unknown",
        "warnings": [],
        "used_mode": "",
        "used_fallback": False,
        "reference_heading_found": False,
        "text_preview": "",
        "extracted_citation_raw": [],
        "actual_citation_keys": [],
        "expected_citation_keys": _normalize_key_list(expected.get("citation_keys")),
        "matching_asserted": False,
        "matching_skipped_reason": "",
        "invalid_expected_matching": False,
        "invalid_expected_matching_violations": [],
        "expected_matching": {},
        "actual_matching": {},
        "matching_diffs": {},
    }

    if not file_name:
        base_result["status"] = "skipped"
        base_result["reason"] = "missing_file_name"
        return base_result

    file_path = DOCS_DIR / file_name
    if not file_path.exists():
        base_result["status"] = "skipped"
        base_result["reason"] = "missing_file"
        base_result["warnings"].append(f"Missing fixture file: {file_path}")
        return base_result

    if not base_result["expected_citation_keys"]:
        base_result["status"] = "skipped"
        base_result["reason"] = "missing_expected_citation_keys"
        base_result["warnings"].append("expected.citation_keys is required for assertion")
        return base_result

    try:
        full_text = _load_document_text(file_path)
    except Exception as e:
        base_result["status"] = "failed"
        base_result["reason"] = f"load_document_failed: {e.__class__.__name__}: {e}"
        return base_result

    body_meta = _extract_body_text(full_text, case.get("body_extract", {}))
    body_text = body_meta["body_text"]
    base_result["used_mode"] = body_meta["used_mode"]
    base_result["used_fallback"] = body_meta["used_fallback"]
    base_result["reference_heading_found"] = body_meta["reference_heading_found"]
    base_result["text_preview"] = _preview(body_text)

    try:
        extracted = extract_citations(body_text)
        extracted_raw = [str(item.get("raw", "")).strip() for item in extracted if str(item.get("raw", "")).strip()]
        actual_citation_keys = []
        for citation in extracted:
            parsed = parse_citation(citation)
            key = build_citation_key(parsed)
            if key:
                actual_citation_keys.append(key)
        base_result["extracted_citation_raw"] = extracted_raw
        base_result["actual_citation_keys"] = sorted(set(actual_citation_keys))
    except Exception as e:
        base_result["status"] = "failed"
        base_result["reason"] = f"citation_pipeline_failed: {e.__class__.__name__}: {e}"
        return base_result

    citation_pass = base_result["actual_citation_keys"] == base_result["expected_citation_keys"]

    expected_matching = expected.get("matching")
    matching_pass = True
    if expected_matching is not None:
        violations = _validate_matching_expected(expected_matching, base_result["expected_citation_keys"])
        if violations:
            base_result["invalid_expected_matching"] = True
            base_result["invalid_expected_matching_violations"] = violations
            base_result["matching_skipped_reason"] = "invalid_expected_matching"
            base_result["warnings"].append("matching assertion skipped because expected.matching is inconsistent")
            matching_pass = True
        else:
            base_result["matching_asserted"] = True
            references = case.get("references", []) if isinstance(case.get("references", []), list) else []
            references = [str(item) for item in references]
            expected_norm = {
                "matched": _normalize_key_list(expected_matching.get("matched")),
                "missing_in_reference": _normalize_key_list(expected_matching.get("missing_in_reference")),
                "extra_in_reference": _normalize_key_list(expected_matching.get("extra_in_reference")),
                "ambiguous": _normalize_ambiguous_expected(expected_matching.get("ambiguous", [])),
            }
            base_result["expected_matching"] = expected_norm

            try:
                actual_matching_raw = match_citations(body_text, references)
            except Exception as e:
                base_result["status"] = "failed"
                base_result["reason"] = f"matching_pipeline_failed: {e.__class__.__name__}: {e}"
                return base_result

            actual_norm = {
                "matched": _normalize_key_list(actual_matching_raw.get("matched")),
                "missing_in_reference": _normalize_key_list(actual_matching_raw.get("missing_in_reference")),
                "extra_in_reference": _normalize_key_list(actual_matching_raw.get("extra_in_reference")),
                "ambiguous": _normalize_ambiguous_actual(actual_matching_raw.get("ambiguous", [])),
            }
            base_result["actual_matching"] = actual_norm

            diffs = {}
            if actual_norm["matched"] != expected_norm["matched"]:
                diffs["matched"] = {"expected": expected_norm["matched"], "actual": actual_norm["matched"]}
            if actual_norm["missing_in_reference"] != expected_norm["missing_in_reference"]:
                diffs["missing_in_reference"] = {
                    "expected": expected_norm["missing_in_reference"],
                    "actual": actual_norm["missing_in_reference"],
                }
            if actual_norm["extra_in_reference"] != expected_norm["extra_in_reference"]:
                diffs["extra_in_reference"] = {
                    "expected": expected_norm["extra_in_reference"],
                    "actual": actual_norm["extra_in_reference"],
                }

            ambiguous_diff = _compare_ambiguous(expected_norm["ambiguous"], actual_matching_raw.get("ambiguous", []))
            if ambiguous_diff:
                diffs["ambiguous"] = ambiguous_diff

            base_result["matching_diffs"] = diffs
            matching_pass = len(diffs) == 0

    if citation_pass and matching_pass:
        base_result["status"] = "passed"
        base_result["reason"] = "ok"
    else:
        base_result["status"] = "failed"
        base_result["reason"] = "citation_keys_mismatch" if not citation_pass else "matching_mismatch"

    return base_result


def _write_report(results: list[dict], report_path: Path, dataset_version: int | None):
    total = len(results)
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    skipped_missing_file = sum(1 for result in results if result["status"] == "skipped" and result["reason"] == "missing_file")
    skipped_missing_expected = sum(
        1
        for result in results
        if result["status"] == "skipped" and result["reason"] in {"missing_expected_citation_keys", "missing_file_name"}
    )
    invalid_expected_matching = sum(1 for result in results if result.get("invalid_expected_matching"))

    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Document Matching Regression Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append(f"- Dataset version: {dataset_version if dataset_version is not None else 'unknown'}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total: {total}")
    lines.append(f"- passed: {passed}")
    lines.append(f"- failed: {failed}")
    lines.append(f"- skipped: {skipped}")
    lines.append(f"- skipped_missing_file: {skipped_missing_file}")
    lines.append(f"- skipped_missing_expected: {skipped_missing_expected}")
    lines.append(f"- invalid_expected_matching: {invalid_expected_matching}")
    lines.append("")

    failed_cases = [result for result in results if result["status"] == "failed"]
    lines.append("## Failures")
    lines.append("")
    if not failed_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in failed_cases:
            lines.append(f"### {case['id']} {case['name']}")
            lines.append("")
            lines.append(f"- file: {case['file']}")
            lines.append(f"- reason: {case['reason']}")
            lines.append(f"- used_mode: {case['used_mode']}")
            lines.append(f"- used_fallback: {case['used_fallback']}")
            lines.append(f"- reference_heading_found: {case['reference_heading_found']}")
            lines.append(f"- text_preview: {case['text_preview']}")
            lines.append(f"- extracted_citation_raw_preview: {_preview(' | '.join(case['extracted_citation_raw']))}")
            lines.append(f"- expected_citation_keys: {case['expected_citation_keys']}")
            lines.append(f"- actual_citation_keys: {case['actual_citation_keys']}")
            if case.get("matching_asserted"):
                lines.append("- expected_matching:")
                lines.append("```json")
                lines.append(json.dumps(case.get("expected_matching", {}), ensure_ascii=False, indent=2))
                lines.append("```")
                lines.append("- actual_matching:")
                lines.append("```json")
                lines.append(json.dumps(case.get("actual_matching", {}), ensure_ascii=False, indent=2))
                lines.append("```")
                lines.append("- matching_diffs:")
                lines.append("```json")
                lines.append(json.dumps(case.get("matching_diffs", {}), ensure_ascii=False, indent=2))
                lines.append("```")
            else:
                lines.append(f"- matching_skipped_reason: {case.get('matching_skipped_reason', '')}")
                if case.get("invalid_expected_matching_violations"):
                    lines.append("- invalid_expected_matching_violations:")
                    lines.append("```json")
                    lines.append(json.dumps(case["invalid_expected_matching_violations"], ensure_ascii=False, indent=2))
                    lines.append("```")
            if case.get("warnings"):
                lines.append("- warnings:")
                lines.append("```json")
                lines.append(json.dumps(case["warnings"], ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")

    skipped_cases = [result for result in results if result["status"] == "skipped"]
    lines.append("## Skipped")
    lines.append("")
    if not skipped_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in skipped_cases:
            lines.append(f"- {case['id']} {case['name']} ({case['file']}): {case['reason']}")
        lines.append("")

    invalid_cases = [result for result in results if result.get("invalid_expected_matching")]
    lines.append("## Invalid Expected Matching")
    lines.append("")
    if not invalid_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in invalid_cases:
            lines.append(f"### {case['id']} {case['name']}")
            lines.append("")
            lines.append(f"- matching_skipped_reason: {case.get('matching_skipped_reason', '')}")
            lines.append("- violations:")
            lines.append("```json")
            lines.append(json.dumps(case.get("invalid_expected_matching_violations", []), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        return

    try:
        payload = json.loads(CASES_PATH.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"Failed to read document matching cases JSON: {e}")
        return

    if isinstance(payload, dict):
        cases = payload.get("cases", [])
        version = payload.get("version")
    elif isinstance(payload, list):
        cases = payload
        version = None
    else:
        print("Invalid cases format: expected object with cases[] or direct list")
        return

    if version != 1:
        print(f"[WARN] Unexpected dataset version: {version}. Expected version=1.")

    if not isinstance(cases, list):
        print("Invalid cases format: cases must be a list")
        return

    results = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        result = _run_case(case)
        results.append(result)
        status = result["status"].upper()
        print(f"[{status}] {result['id']} {result['name']} ({result['file']})")
        if result.get("warnings"):
            for warning in result["warnings"]:
                print(f"  [WARN] {warning}")

    _write_report(results, REPORT_PATH, version if isinstance(version, int) else None)

    total = len(results)
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    invalid_expected_matching = sum(1 for result in results if result.get("invalid_expected_matching"))

    print("---")
    print(f"Total: {total}")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"SKIPPED: {skipped}")
    print(f"INVALID_EXPECTED_MATCHING: {invalid_expected_matching}")
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
