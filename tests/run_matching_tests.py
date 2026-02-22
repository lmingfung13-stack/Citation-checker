import json
import argparse
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from citation_core import (
    DocParagraph,
    citation_key,
    extract_intext_citations,
    extract_reference_items,
    find_reference_section_start,
    match_citations_to_refs,
    normalize_text,
    parse_reference_item,
    read_docx_bytes,
    read_pdf_bytes,
    reference_key,
)

TESTS_DIR = Path(__file__).resolve().parent
DOCS_DIR = TESTS_DIR / "datasets" / "matching" / "docs"
CASES_PATH = TESTS_DIR / "datasets" / "matching" / "matching_cases.json"
EXPECTED_DIR = TESTS_DIR / "datasets" / "matching" / "expected"
LEVEL1_EXPECTED_PATH = EXPECTED_DIR / "level1_expected.json"
LEVEL2_EXPECTED_PATH = EXPECTED_DIR / "level2_expected.json"
LEVEL3_EXPECTED_PATH = EXPECTED_DIR / "level3_expected.json"
REPORT_PATH = TESTS_DIR / "matching_test_report.md"
REPORT_LEVEL1_PATH = TESTS_DIR / "matching_test_report_level1.md"
REPORT_LEVEL2_PATH = TESTS_DIR / "matching_test_report_level2.md"
REPORT_LEVEL3_PATH = TESTS_DIR / "matching_test_report_level3.md"
DEFAULT_HEADINGS = ["References", "REFERENCES", "Bibliography", "參考文獻", "参考文献"]
DEFAULT_MAX_CHARS = 120000


def _normalize_key_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    keys = [str(v).strip() for v in values if str(v).strip()]
    return sorted(set(keys))


def _normalize_key_count_map(values) -> dict[str, int]:
    if not isinstance(values, dict):
        return {}

    normalized = {}
    for raw_key, raw_count in values.items():
        key = str(raw_key).strip()
        if not key:
            continue
        try:
            count = int(raw_count)
        except Exception:
            continue
        if count <= 0:
            continue
        normalized[key] = count
    return dict(sorted(normalized.items()))


def _safe_ratio(num: int, den: int) -> float:
    if den == 0:
        return 0.0
    return num / den


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _fmt_score(value: float | None, asserted: bool = True) -> str:
    if not asserted or value is None:
        return "n/a"
    return f"{value:.4f}"


def _compute_similarity(expected_keys: list[str], actual_keys: list[str]) -> dict:
    expected_set = set(expected_keys or [])
    actual_set = set(actual_keys or [])
    overlap = expected_set & actual_set
    union = expected_set | actual_set

    if not expected_set and not actual_set:
        precision = 1.0
        recall = 1.0
        f1 = 1.0
        jaccard = 1.0
    else:
        precision = _safe_ratio(len(overlap), len(actual_set))
        recall = _safe_ratio(len(overlap), len(expected_set))
        f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) > 0 else 0.0
        jaccard = _safe_ratio(len(overlap), len(union))

    return {
        "expected_count": len(expected_set),
        "actual_count": len(actual_set),
        "overlap_count": len(overlap),
        "missing_keys": sorted(expected_set - actual_set),
        "extra_keys": sorted(actual_set - expected_set),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "jaccard": jaccard,
    }


def _compute_count_similarity(expected_counts: dict[str, int], actual_counts: dict[str, int]) -> dict:
    expected = _normalize_key_count_map(expected_counts)
    actual = _normalize_key_count_map(actual_counts)
    all_keys = sorted(set(expected) | set(actual))

    expected_total = sum(expected.values())
    actual_total = sum(actual.values())
    overlap_total = sum(min(expected.get(k, 0), actual.get(k, 0)) for k in all_keys)

    if expected_total == 0 and actual_total == 0:
        precision = 1.0
        recall = 1.0
        f1 = 1.0
    else:
        precision = _safe_ratio(overlap_total, actual_total)
        recall = _safe_ratio(overlap_total, expected_total)
        f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) > 0 else 0.0

    mismatch_keys = {}
    for key in all_keys:
        exp = expected.get(key, 0)
        act = actual.get(key, 0)
        if exp == act:
            continue
        mismatch_keys[key] = {"expected": exp, "actual": act, "delta": act - exp}

    return {
        "count_expected_total": expected_total,
        "count_actual_total": actual_total,
        "count_overlap_total": overlap_total,
        "count_precision": precision,
        "count_recall": recall,
        "count_f1": f1,
        "count_mismatch_keys": mismatch_keys,
    }


def _finalize_layer(layer: dict) -> None:
    metrics = _compute_similarity(layer.get("expected_keys", []), layer.get("actual_keys", []))
    layer.update(metrics)

    if not layer.get("asserted", False):
        layer["passed"] = True
        layer["status"] = "not_asserted"
        return

    exact_match = (len(layer.get("missing_keys", [])) == 0 and len(layer.get("extra_keys", [])) == 0)
    layer["passed"] = exact_match
    layer["status"] = "passed" if exact_match else "failed"


def _finalize_level1_layer(layer: dict) -> None:
    _finalize_layer(layer)

    expected_counts = _normalize_key_count_map(layer.get("expected_key_counts"))
    actual_counts = _normalize_key_count_map(layer.get("actual_key_counts"))
    layer["expected_key_counts"] = expected_counts
    layer["actual_key_counts"] = actual_counts

    if not layer.get("asserted", False):
        layer["count_asserted"] = False
        layer["count_passed"] = True
        layer["count_status"] = "not_asserted"
        layer["count_expected_total"] = sum(expected_counts.values())
        layer["count_actual_total"] = sum(actual_counts.values())
        layer["count_overlap_total"] = 0
        layer["count_precision"] = 1.0
        layer["count_recall"] = 1.0
        layer["count_f1"] = 1.0
        layer["count_mismatch_keys"] = {}
        return

    count_asserted = bool(layer.get("count_asserted", False))
    layer["count_asserted"] = count_asserted
    if not count_asserted:
        layer["count_passed"] = True
        layer["count_status"] = "not_asserted"
        layer["count_expected_total"] = sum(expected_counts.values())
        layer["count_actual_total"] = sum(actual_counts.values())
        layer["count_overlap_total"] = 0
        layer["count_precision"] = 1.0
        layer["count_recall"] = 1.0
        layer["count_f1"] = 1.0
        layer["count_mismatch_keys"] = {}
        return

    count_metrics = _compute_count_similarity(expected_counts, actual_counts)
    layer.update(count_metrics)
    count_match = len(count_metrics.get("count_mismatch_keys", {})) == 0
    layer["count_passed"] = count_match
    layer["count_status"] = "passed" if count_match else "failed"

    layer["passed"] = bool(layer.get("passed", False) and count_match)
    layer["status"] = "passed" if layer["passed"] else "failed"


def _normalize_free_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _normalize_for_boundary(text: str) -> str:
    if text is None:
        return ""

    full_to_half = str.maketrans(
        {
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
        }
    )

    normalized = str(text).translate(full_to_half)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def _compute_boundary_metrics(expected_items: list[str], predicted_items: list[str]) -> dict:
    from difflib import SequenceMatcher

    normalized_expected = [_normalize_for_boundary(x) for x in expected_items if _normalize_for_boundary(x)]
    normalized_predicted = [_normalize_for_boundary(x) for x in predicted_items if _normalize_for_boundary(x)]

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
    precision = _safe_ratio(matched_count, total_pred)
    recall = _safe_ratio(matched_count, total_exp)
    f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _contains_loose(actual_text: str, expected_snippet: str) -> bool:
    actual = _normalize_free_text(actual_text)
    expected = _normalize_free_text(expected_snippet)
    if not expected:
        return False
    if expected in actual:
        return True
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", expected)
    if not tokens:
        return False
    return all(tok in actual for tok in tokens)


def _extract_author_surnames(raw_norm: str) -> list[str]:
    year_match = re.search(r"\(([^)]+)\)", raw_norm)
    author_segment = raw_norm[: year_match.start()].strip(" ,;:.") if year_match else raw_norm
    if not author_segment:
        return []

    # English style: "Surname, X., Surname, Y., & Surname, Z."
    en_hits = re.findall(r"([A-Za-z][A-Za-z'`\-]+)\s*,\s*[A-Za-z]", author_segment)
    if en_hits:
        out = []
        seen = set()
        for h in en_hits:
            k = h.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(h)
        return out

    # Chinese style fallback: split by connectors before year.
    zh_tokens = re.split(r"(?:、|,|，|;|&|與|和|及|\band\b)+", author_segment, flags=re.IGNORECASE)
    out = []
    seen = set()
    for tok in zh_tokens:
        cleaned = re.sub(r"[\s\.\(\)]+", "", tok)
        if not cleaned:
            continue
        k = cleaned.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(cleaned)
    return out


def _extract_reference_components(raw_text: str, ref_obj) -> dict:
    raw = str(raw_text or "").strip()
    raw_norm = re.sub(r"\s+", " ", raw).strip()
    parser_author1 = str(getattr(ref_obj, "author1", "") or "").strip()
    parser_author2 = str(getattr(ref_obj, "author2", "") or "").strip()
    year = str(getattr(ref_obj, "year", "") or "").strip()
    authors = _extract_author_surnames(raw_norm)
    author1 = authors[0] if authors else parser_author1
    author2 = authors[1] if len(authors) >= 2 else parser_author2

    title = ""
    journal = ""
    source = ""

    year_match = re.search(r"\(([^)]+)\)", raw_norm)
    tail = raw_norm
    if year_match:
        tail = raw_norm[year_match.end() :].strip(" .,-;:()")

    if tail:
        source = tail.strip(" ,;:()")
        sentence_split = re.split(r"[。\.]\s*", tail, maxsplit=1)
        title = sentence_split[0].strip(" ,;:()")
        remainder = sentence_split[1].strip(" ,;:()") if len(sentence_split) > 1 else ""
        if remainder:
            journal = re.split(r"\s*,\s*", remainder, maxsplit=1)[0].strip()
        elif "," in title:
            # Fallback for references without clear period after title.
            title_head, title_tail = title.split(",", 1)
            title = title_head.strip()
            journal = title_tail.strip()

    return {
        "author1": author1,
        "author2": author2,
        "authors": authors,
        "author_count": len(authors),
        "year": year,
        "source": source,
        "title": title,
        "journal": journal,
        "raw": raw_norm,
    }


def _build_reference_spans(reference_section_text: str, refs) -> dict:
    spans = []
    spans_by_key = {}
    spans_by_item_idx = {}
    components_by_key = {}
    components_by_item_idx = {}
    duplicate_keys = []

    cursor = 0
    text = normalize_text(reference_section_text or "").lower()

    for ref in refs or []:
        key = _tuple_to_key(reference_key(ref))
        item_idx = int(getattr(ref, "item_idx", -1))
        if item_idx < 0:
            continue

        raw_original = normalize_text(str(ref.raw or ""))
        raw_search = raw_original.lower()
        start = text.find(raw_search, cursor) if raw_search else -1
        end = -1
        found = False
        match_mode = "exact"

        if start >= 0:
            end = start + len(raw_search)
            found = True
            cursor = end
        elif raw_search:
            token_pattern = r"\s+".join(re.escape(tok) for tok in raw_search.split())
            if token_pattern:
                m = re.search(token_pattern, text[cursor:])
                if m:
                    start = cursor + m.start()
                    end = cursor + m.end()
                    found = True
                    cursor = end
                    match_mode = "token"

        if not found and raw_search:
            # Fallback: attempt global token search when local search misses due OCR/layout drift.
            token_pattern = r"\s+".join(re.escape(tok) for tok in raw_search.split()[:12])
            if token_pattern:
                m = re.search(token_pattern, text)
                if m:
                    start = m.start()
                    end = m.end()
                    found = True
                    cursor = max(cursor, end)
                    match_mode = "global_token"

        if not found:
            # Last resort: still provide deterministic span so position layer can cover every item.
            start = cursor
            end = start + len(raw_search)
            cursor = end + 1
            found = True
            match_mode = "synthetic"

        span = {
            "item_idx": item_idx,
            "key": key,
            "start": int(start) if start >= 0 else -1,
            "end": int(end) if end >= 0 else -1,
            "found": bool(found),
            "match_mode": match_mode,
            "page": int(getattr(ref, "page", -1)),
        }
        spans.append(span)
        spans_by_item_idx[item_idx] = span

        comp = _extract_reference_components(raw_original, ref)
        components_by_item_idx[item_idx] = comp
        if key:
            if key in spans_by_key:
                duplicate_keys.append(key)
            else:
                spans_by_key[key] = span
                components_by_key[key] = comp

    title_detected = sum(1 for comp in components_by_item_idx.values() if str(comp.get("title", "")).strip())
    journal_detected = sum(1 for comp in components_by_item_idx.values() if str(comp.get("journal", "")).strip())
    source_detected = sum(1 for comp in components_by_item_idx.values() if str(comp.get("source", "")).strip())
    total = len(components_by_item_idx)

    coverage = {
        "total_items": total,
        "source_detected_count": source_detected,
        "source_detected_ratio": _safe_ratio(source_detected, total),
        "title_detected_count": title_detected,
        "journal_detected_count": journal_detected,
        "title_detected_ratio": _safe_ratio(title_detected, total),
        "journal_detected_ratio": _safe_ratio(journal_detected, total),
    }

    return {
        "spans": spans,
        "spans_by_key": spans_by_key,
        "spans_by_item_idx": spans_by_item_idx,
        "components_by_key": components_by_key,
        "components_by_item_idx": components_by_item_idx,
        "duplicate_keys": sorted(set(duplicate_keys)),
        "coverage": coverage,
    }


def _evaluate_position_assertion(expected_positions, spans_by_key: dict, spans_by_item_idx: dict, components_by_item_idx: dict) -> dict:
    if not isinstance(expected_positions, list):
        return {
            "asserted": False,
            "status": "not_asserted",
            "passed": True,
            "expected_count": 0,
            "actual_count": 0,
            "matched_count": 0,
            "missing_keys": [],
            "mismatch_keys": [],
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        }

    ordered_actual = [
        s
        for s in sorted(
            [x for x in spans_by_item_idx.values() if isinstance(x, dict)],
            key=lambda x: (x.get("start", -1), x.get("item_idx", -1)),
        )
        if isinstance(s.get("item_idx"), int)
    ]
    order_map = {s.get("item_idx"): idx for idx, s in enumerate(ordered_actual)}
    ordered_actual_texts = []
    for s in ordered_actual:
        comp = components_by_item_idx.get(s.get("item_idx"), {})
        ordered_actual_texts.append(str(comp.get("raw", "") if isinstance(comp, dict) else ""))

    # Human-maintained mode: answer is full pasted item list (raw-pastes style).
    # We keep strict boundary checking by requiring same count + same order + exact normalized item text.
    if all(not isinstance(entry, dict) for entry in expected_positions):
        expected_items = [str(x).strip() for x in expected_positions if str(x).strip()]
        expected_norm = [_normalize_for_boundary(x) for x in expected_items]
        actual_norm = [_normalize_for_boundary(x) for x in ordered_actual_texts]

        exact_match_count = 0
        mismatch_keys = []
        missing_keys = []
        extra_keys = []
        shared = min(len(expected_norm), len(actual_norm))

        for idx in range(shared):
            if expected_norm[idx] == actual_norm[idx]:
                exact_match_count += 1
            else:
                mismatch_keys.append(f"order:{idx}")

        for idx in range(shared, len(expected_norm)):
            missing_keys.append(f"order:{idx}")
        for idx in range(shared, len(actual_norm)):
            extra_keys.append(f"order:{idx}")

        strict_passed = (
            len(expected_norm) == len(actual_norm)
            and exact_match_count == len(expected_norm)
        )
        metrics = _compute_boundary_metrics(expected_items, ordered_actual_texts)

        return {
            "asserted": True,
            "status": "passed" if strict_passed else "failed",
            "passed": strict_passed,
            "mode": "strict_pasted_items",
            "expected_count": len(expected_norm),
            "actual_count": len(actual_norm),
            "matched_count": exact_match_count,
            "missing_keys": missing_keys,
            "mismatch_keys": mismatch_keys,
            "extra_keys": extra_keys,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "strict_exact_ratio": _safe_ratio(exact_match_count, len(expected_norm)),
        }

    expected_count = 0
    actual_count = 0
    matched_count = 0
    missing_keys = []
    mismatch_keys = []

    for entry in expected_positions:
        if not isinstance(entry, dict):
            continue
        item_idx = entry.get("item_idx")
        key = str(entry.get("key", "")).strip()
        if item_idx is None and not key:
            continue
        expected_count += 1
        label = f"item_idx:{item_idx}" if item_idx is not None else key
        if item_idx is not None:
            try:
                actual = spans_by_item_idx.get(int(item_idx))
            except Exception:
                actual = None
        else:
            actual = spans_by_key.get(key)
        if actual is None or not actual.get("found", False):
            missing_keys.append(label)
            continue
        actual_count += 1
        try:
            exp_start = int(entry.get("start"))
            exp_end = int(entry.get("end"))
            has_numeric = True
        except Exception:
            has_numeric = False

        checks = []

        if has_numeric:
            tol = int(entry.get("tolerance", 40))
            checks.append(abs(actual["start"] - exp_start) <= tol and abs(actual["end"] - exp_end) <= tol)

        if "order" in entry:
            try:
                exp_order = int(entry.get("order"))
                act_order = order_map.get(actual.get("item_idx"), -1)
                checks.append(act_order == exp_order)
            except Exception:
                checks.append(False)

        if "contains" in entry:
            expected_snippet = str(entry.get("contains", "") or "")
            comp = components_by_item_idx.get(actual.get("item_idx"))
            actual_raw = str(comp.get("raw", "") if isinstance(comp, dict) else "")
            checks.append(_contains_loose(actual_raw, expected_snippet))

        # If no explicit checks are provided, fallback to existence check.
        if not checks:
            checks.append(True)

        if all(checks):
            matched_count += 1
        else:
            mismatch_keys.append(label)

    precision = _safe_ratio(matched_count, actual_count)
    recall = _safe_ratio(matched_count, expected_count)
    f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) > 0 else 0.0
    passed = (expected_count > 0 and matched_count == expected_count) or (expected_count == 0)

    return {
        "asserted": True,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "expected_count": expected_count,
        "actual_count": actual_count,
        "matched_count": matched_count,
        "missing_keys": sorted(set(missing_keys)),
        "mismatch_keys": sorted(set(mismatch_keys)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _evaluate_parsed_assertion(expected_parsed, components_by_key: dict, components_by_item_idx: dict) -> dict:
    if not isinstance(expected_parsed, list):
        return {
            "asserted": False,
            "status": "not_asserted",
            "passed": True,
            "expected_items": 0,
            "matched_items": 0,
            "expected_fields": 0,
            "matched_fields": 0,
            "field_accuracy": 1.0,
            "failed_keys": [],
        }

    expected_items = 0
    matched_items = 0
    expected_fields = 0
    matched_fields = 0
    failed_keys = []

    for entry in expected_parsed:
        if not isinstance(entry, dict):
            continue
        item_idx = entry.get("item_idx")
        key = str(entry.get("key", "")).strip()
        if item_idx is None and not key:
            continue
        expected_items += 1
        label = f"item_idx:{item_idx}" if item_idx is not None else key
        if item_idx is not None:
            try:
                comp = components_by_item_idx.get(int(item_idx))
            except Exception:
                comp = None
        else:
            comp = components_by_key.get(key)
        if not comp:
            failed_keys.append(label)
            continue

        item_expected_fields = 0
        item_matched_fields = 0

        def _check_field(field_name: str, mode: str = "contains"):
            nonlocal expected_fields, matched_fields, item_expected_fields, item_matched_fields
            if field_name not in entry:
                return
            expected_value = _normalize_free_text(entry.get(field_name, ""))
            actual_value = _normalize_free_text(comp.get(field_name, ""))
            expected_fields += 1
            item_expected_fields += 1
            ok = False
            if mode == "eq":
                ok = actual_value == expected_value
            else:
                ok = expected_value in actual_value if expected_value else False
            if ok:
                matched_fields += 1
                item_matched_fields += 1

        def _check_authors_list():
            nonlocal expected_fields, matched_fields, item_expected_fields, item_matched_fields
            if "authors" not in entry:
                return
            expected_value = entry.get("authors")
            actual_authors = comp.get("authors", [])
            if not isinstance(actual_authors, list):
                actual_authors = []
            actual_norm = [_normalize_free_text(x) for x in actual_authors if str(x).strip()]

            expected_list = expected_value if isinstance(expected_value, list) else [expected_value]
            expected_norm = [_normalize_free_text(x) for x in expected_list if str(x).strip()]
            for need in expected_norm:
                expected_fields += 1
                item_expected_fields += 1
                ok = any(need == got or (need and need in got) for got in actual_norm)
                if ok:
                    matched_fields += 1
                    item_matched_fields += 1

        def _check_source_field():
            nonlocal expected_fields, matched_fields, item_expected_fields, item_matched_fields
            if "source" not in entry:
                return
            expected_source = _normalize_free_text(entry.get("source", ""))

            actual_source = _normalize_free_text(comp.get("source", ""))
            expected_fields += 1
            item_expected_fields += 1
            ok = expected_source in actual_source if expected_source else False
            if ok:
                matched_fields += 1
                item_matched_fields += 1

        _check_field("author1", mode="contains")
        _check_field("author2", mode="contains")
        _check_authors_list()
        _check_field("year", mode="contains")
        _check_source_field()

        if item_expected_fields > 0 and item_expected_fields == item_matched_fields:
            matched_items += 1
        elif item_expected_fields > 0:
            failed_keys.append(label)

    field_accuracy = _safe_ratio(matched_fields, expected_fields)
    passed = expected_items == matched_items and expected_fields == matched_fields

    return {
        "asserted": True,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "expected_items": expected_items,
        "matched_items": matched_items,
        "expected_fields": expected_fields,
        "matched_fields": matched_fields,
        "field_accuracy": field_accuracy,
        "failed_keys": sorted(set(failed_keys)),
    }


def _finalize_level2_source(layer: dict) -> None:
    layer["key_status"] = layer.get("status", "not_asserted")
    statuses = [layer["key_status"]]
    if layer.get("position", {}).get("asserted", False):
        statuses.append(layer["position"]["status"])
    if layer.get("parsed_fields", {}).get("asserted", False):
        statuses.append(layer["parsed_fields"]["status"])

    if any(s == "failed" for s in statuses):
        layer["status"] = "failed"
        layer["passed"] = False
    elif all(s == "not_asserted" for s in statuses):
        layer["status"] = "not_asserted"
        layer["passed"] = True
    else:
        layer["status"] = "passed"
        layer["passed"] = True

def _preview(text: str, limit: int = 160) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _normalize_author_token(value: str) -> str:
    token = unicodedata.normalize("NFKC", str(value or "").strip().lower())
    token = token.replace("’", "'").replace("`", "'").replace("ˇ", "")
    token = token.replace("'", "")
    token = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", token)
    return token


def _normalize_year_token(value: str) -> str:
    token = unicodedata.normalize("NFKC", str(value or "").strip().lower())
    token = token.replace(" ", "")
    if "n.d" in token or "nodate" in token:
        return "nd"
    if "inpress" in token or "press" in token:
        return "inpress"
    m = re.search(r"((?:19|20)\d{2}[a-z]?)", token)
    if m:
        return m.group(1)
    return re.sub(r"[^a-z0-9]+", "", token)


def _build_key(author: str, year: str) -> str:
    author_token = _normalize_author_token(author)
    year_token = _normalize_year_token(year)
    if not author_token or not year_token:
        return ""
    return f"{author_token}_{year_token}"


def _tuple_to_key(key_tuple) -> str:
    if not key_tuple or len(key_tuple) < 4:
        return ""
    _, author1, _, year = key_tuple
    return _build_key(author1, year)


def _sanitize_citation_author(author: str) -> str:
    raw = unicodedata.normalize("NFKC", str(author or "")).strip()
    if not raw:
        return ""

    # Keep original behavior for normal names; only de-noise obvious sentence-lead noise.
    tokens = re.findall(r"[A-Za-z][A-Za-z'`\-]*", raw)
    if not tokens:
        return raw

    stopwords = {
        "this",
        "our",
        "the",
        "we",
        "study",
        "paper",
        "research",
        "analysis",
        "evidence",
        "result",
        "results",
        "finding",
        "findings",
        "following",
        "follows",
        "based",
        "according",
        "consistent",
        "and",
        "one",
        "notable",
        "exception",
        "is",
        "see",
        "review",
        "by",
        "eg",
        "e",
        "g",
    }

    if tokens[0].lower() in stopwords:
        filtered = [t for t in tokens if t.lower() not in stopwords]
        if filtered:
            return filtered[0]
    return raw


def _collect_citation_key_counts(citations) -> dict[str, int]:
    counter = Counter()
    for c in citations or []:
        key_tuple = citation_key(c)
        if not key_tuple or len(key_tuple) < 4:
            continue
        lang, author1, author2, year = key_tuple
        year_token = _normalize_year_token(year)
        if not re.match(r"^(19|20)\d{2}[a-z]?$", year_token):
            continue
        author1 = _sanitize_citation_author(author1)
        k = _tuple_to_key((lang, author1, author2, year))
        if k:
            author_token = k.split("_", 1)[0]
            if len(author_token) < 2 or author_token.isdigit():
                continue
            counter[k] += 1
    return dict(sorted(counter.items()))


def _collect_citation_keys(citations) -> list[str]:
    return sorted(_collect_citation_key_counts(citations).keys())


def _collect_reference_keys(refs) -> list[str]:
    keys = []
    for r in refs or []:
        k = _tuple_to_key(reference_key(r))
        if k:
            keys.append(k)
    return sorted(set(keys))


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


def _load_document(path: Path) -> list[DocParagraph]:
    suffix = path.suffix.lower()
    file_bytes = path.read_bytes()

    if suffix == ".pdf":
        return read_pdf_bytes(file_bytes)
    if suffix == ".docx":
        return read_docx_bytes(file_bytes)
    raise ValueError(f"Unsupported file extension: {suffix}")


def _to_body_paragraphs(body_text: str) -> list[DocParagraph]:
    return [DocParagraph(line, 1) for line in (body_text or "").split("\n") if str(line).strip()]


def _parse_manual_references(reference_lines: list[str]):
    parsed_refs = []
    failed_refs = []
    for idx, line in enumerate(reference_lines):
        txt = str(line).strip()
        if not txt:
            continue
        parsed = parse_reference_item(txt, idx, 0)
        if parsed is None:
            failed_refs.append(txt)
            continue
        parsed_refs.append(parsed)
    return parsed_refs, failed_refs


def _run_case(case: dict, expected: dict, run_layer: str = "all") -> dict:
    case_id = str(case.get("id", "")).strip()
    name = str(case.get("name", "")).strip()
    file_name = str(case.get("file", "")).strip()
    expected = expected if isinstance(expected, dict) else {}

    result = {
        "id": case_id,
        "name": name,
        "file": file_name,
        "status": "failed",
        "reason": "unknown",
        "warnings": [],
        "used_mode": "",
        "used_fallback": False,
        "reference_heading_found": False,
        "text_preview": "",
        "level1": {
            "asserted": True,
            "passed": False,
            "status": "pending",
            "expected_keys": _normalize_key_list(expected.get("level1_citation_keys")),
            "actual_keys": [],
            "expected_key_counts": _normalize_key_count_map(expected.get("level1_citation_key_counts")),
            "actual_key_counts": {},
            "count_asserted": "level1_citation_key_counts" in expected,
            "count_passed": True,
            "count_status": "not_asserted",
            "count_expected_total": 0,
            "count_actual_total": 0,
            "count_overlap_total": 0,
            "count_precision": 1.0,
            "count_recall": 1.0,
            "count_f1": 1.0,
            "count_mismatch_keys": {},
            "expected_count": 0,
            "actual_count": 0,
            "overlap_count": 0,
            "missing_keys": [],
            "extra_keys": [],
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "jaccard": 0.0,
        },
        "level2_auto": {
            "asserted": "level2_auto_reference_keys" in expected,
            "passed": True,
            "status": "pending",
            "expected_keys": _normalize_key_list(expected.get("level2_auto_reference_keys")),
            "actual_keys": [],
            "expected_count": 0,
            "actual_count": 0,
            "overlap_count": 0,
            "missing_keys": [],
            "extra_keys": [],
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "jaccard": 0.0,
            "position": {
                "asserted": False,
                "status": "not_asserted",
                "passed": True,
                "expected_count": 0,
                "actual_count": 0,
                "matched_count": 0,
                "missing_keys": [],
                "mismatch_keys": [],
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
            },
            "parsed_fields": {
                "asserted": False,
                "status": "not_asserted",
                "passed": True,
                "expected_items": 0,
                "matched_items": 0,
                "expected_fields": 0,
                "matched_fields": 0,
                "field_accuracy": 1.0,
                "failed_keys": [],
            },
            "parse_coverage": {
                "total_items": 0,
                "title_detected_count": 0,
                "journal_detected_count": 0,
                "title_detected_ratio": 0.0,
                "journal_detected_ratio": 0.0,
            },
            "duplicate_keys": [],
        },
        "level2_manual": {
            "asserted": "level2_manual_reference_keys" in expected,
            "passed": True,
            "status": "pending",
            "expected_keys": _normalize_key_list(expected.get("level2_manual_reference_keys")),
            "actual_keys": [],
            "expected_count": 0,
            "actual_count": 0,
            "manual_parse_failed_count": 0,
            "overlap_count": 0,
            "missing_keys": [],
            "extra_keys": [],
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "jaccard": 0.0,
            "position": {
                "asserted": False,
                "status": "not_asserted",
                "passed": True,
                "expected_count": 0,
                "actual_count": 0,
                "matched_count": 0,
                "missing_keys": [],
                "mismatch_keys": [],
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
            },
            "parsed_fields": {
                "asserted": False,
                "status": "not_asserted",
                "passed": True,
                "expected_items": 0,
                "matched_items": 0,
                "expected_fields": 0,
                "matched_fields": 0,
                "field_accuracy": 1.0,
                "failed_keys": [],
            },
            "parse_coverage": {
                "total_items": 0,
                "title_detected_count": 0,
                "journal_detected_count": 0,
                "title_detected_ratio": 0.0,
                "journal_detected_ratio": 0.0,
            },
            "duplicate_keys": [],
        },
        "level3_info": {
            "matched_count": 0,
            "missing_count": 0,
            "uncited_count": 0,
        },
        "citation_raw_preview": "",
        "reference_raw_preview": "",
    }

    file_path = DOCS_DIR / file_name
    if not file_name:
        result["status"] = "skipped"
        result["reason"] = "missing_file_name"
        return result

    if not file_path.exists():
        result["status"] = "skipped"
        result["reason"] = "missing_file"
        result["warnings"].append(f"missing fixture file: {file_path}")
        return result

    if "level1_citation_keys" not in expected:
        if run_layer in ("all", "level1"):
            result["status"] = "skipped"
            result["reason"] = "missing_expected_level1"
            result["warnings"].append("expected.level1_citation_keys is required")
            return result
        # level2/level3 only runs: do not block by missing level1 expected.
        result["level1"]["asserted"] = False
        result["level1"]["status"] = "not_asserted"
        result["warnings"].append("level1 expected missing; skipped level1 assertion for this run")

    if result["level1"].get("count_asserted"):
        expected_key_set = set(result["level1"]["expected_keys"])
        expected_count_key_set = set(result["level1"]["expected_key_counts"])
        missing_count_keys = sorted(expected_key_set - expected_count_key_set)
        extra_count_keys = sorted(expected_count_key_set - expected_key_set)
        if missing_count_keys:
            result["warnings"].append(
                f"level1 expected count missing keys: {', '.join(missing_count_keys[:5])}"
            )
        if extra_count_keys:
            result["warnings"].append(
                f"level1 expected count has extra keys not in level1_citation_keys: {', '.join(extra_count_keys[:5])}"
            )

    try:
        paragraphs = _load_document(file_path)
    except Exception as e:
        result["status"] = "failed"
        result["reason"] = f"load_document_failed: {e.__class__.__name__}: {e}"
        return result

    full_text = "\n".join((p.text or "") for p in paragraphs if str(p.text or "").strip())
    body_meta = _extract_body_text(full_text, case.get("body_extract", {}))
    result["used_mode"] = body_meta["used_mode"]
    result["used_fallback"] = body_meta["used_fallback"]
    result["reference_heading_found"] = body_meta["reference_heading_found"]
    result["text_preview"] = _preview(body_meta["body_text"])

    body_paras = _to_body_paragraphs(body_meta["body_text"])

    ref_start = find_reference_section_start(paragraphs)
    auto_refs = []
    raw_ref_paras = []
    if ref_start is not None:
        auto_refs = extract_reference_items(paragraphs, ref_start)
        raw_ref_paras = paragraphs[ref_start:]
    else:
        result["warnings"].append("reference heading not found in document")

    citations = extract_intext_citations(body_paras, known_refs=auto_refs)
    citation_key_counts = _collect_citation_key_counts(citations)
    citation_keys = sorted(citation_key_counts.keys())
    result["level1"]["actual_keys"] = citation_keys
    result["level1"]["actual_key_counts"] = citation_key_counts
    result["level1"]["actual_count"] = len(citation_keys)
    result["level1"]["expected_count"] = len(result["level1"]["expected_keys"])
    result["citation_raw_preview"] = _preview(" | ".join(sorted(set(c.raw for c in citations if str(c.raw).strip()))), 400)

    auto_ref_keys = _collect_reference_keys(auto_refs)
    result["level2_auto"]["actual_keys"] = auto_ref_keys
    result["level2_auto"]["actual_count"] = len(auto_ref_keys)
    result["level2_auto"]["expected_count"] = len(result["level2_auto"]["expected_keys"])

    manual_refs_raw = case.get("references", []) if isinstance(case.get("references", []), list) else []
    manual_refs_raw = [str(x) for x in manual_refs_raw if str(x).strip()]
    manual_refs, manual_failed = _parse_manual_references(manual_refs_raw)
    manual_ref_keys = _collect_reference_keys(manual_refs)
    result["level2_manual"]["actual_keys"] = manual_ref_keys
    result["level2_manual"]["actual_count"] = len(manual_ref_keys)
    result["level2_manual"]["expected_count"] = len(result["level2_manual"]["expected_keys"])
    result["level2_manual"]["manual_parse_failed_count"] = len(manual_failed)
    if manual_failed:
        result["warnings"].append(f"manual references parse failed: {len(manual_failed)}")

    auto_ref_section_text = "\n".join(str(p.text or "") for p in raw_ref_paras if str(p.text or "").strip())
    auto_inspection = _build_reference_spans(auto_ref_section_text, auto_refs)
    result["level2_auto"]["parse_coverage"] = auto_inspection["coverage"]
    result["level2_auto"]["duplicate_keys"] = auto_inspection["duplicate_keys"]
    if auto_inspection["duplicate_keys"]:
        result["warnings"].append(f"auto reference duplicate keys: {len(auto_inspection['duplicate_keys'])}")

    manual_ref_section_text = "\n".join(manual_refs_raw)
    manual_inspection = _build_reference_spans(manual_ref_section_text, manual_refs)
    result["level2_manual"]["parse_coverage"] = manual_inspection["coverage"]
    result["level2_manual"]["duplicate_keys"] = manual_inspection["duplicate_keys"]
    if manual_inspection["duplicate_keys"]:
        result["warnings"].append(f"manual reference duplicate keys: {len(manual_inspection['duplicate_keys'])}")

    result["level2_auto"]["position"] = _evaluate_position_assertion(
        expected.get("level2_auto_reference_positions"),
        auto_inspection["spans_by_key"],
        auto_inspection["spans_by_item_idx"],
        auto_inspection["components_by_item_idx"],
    )
    result["level2_auto"]["parsed_fields"] = _evaluate_parsed_assertion(
        expected.get("level2_auto_parsed_fields"),
        auto_inspection["components_by_key"],
        auto_inspection["components_by_item_idx"],
    )
    result["level2_manual"]["position"] = _evaluate_position_assertion(
        expected.get("level2_manual_reference_positions"),
        manual_inspection["spans_by_key"],
        manual_inspection["spans_by_item_idx"],
        manual_inspection["components_by_item_idx"],
    )
    result["level2_manual"]["parsed_fields"] = _evaluate_parsed_assertion(
        expected.get("level2_manual_parsed_fields"),
        manual_inspection["components_by_key"],
        manual_inspection["components_by_item_idx"],
    )

    result["level2_auto"]["asserted"] = bool(
        result["level2_auto"].get("asserted")
        or result["level2_auto"]["position"]["asserted"]
        or result["level2_auto"]["parsed_fields"]["asserted"]
    )
    result["level2_manual"]["asserted"] = bool(
        result["level2_manual"].get("asserted")
        or result["level2_manual"]["position"]["asserted"]
        or result["level2_manual"]["parsed_fields"]["asserted"]
    )

    if auto_refs:
        matched_df, missing_df, uncited_df = match_citations_to_refs(citations, auto_refs, raw_ref_paras)
        result["level3_info"] = {
            "matched_count": int(len(matched_df)),
            "missing_count": int(len(missing_df)),
            "uncited_count": int(len(uncited_df)),
        }
        if not getattr(raw_ref_paras, "__iter__", None):
            result["reference_raw_preview"] = ""
        else:
            result["reference_raw_preview"] = _preview(
                " | ".join(str(p.text or "") for p in raw_ref_paras if str(p.text or "").strip()),
                400,
            )

    _finalize_level1_layer(result["level1"])
    _finalize_layer(result["level2_auto"])
    _finalize_layer(result["level2_manual"])
    _finalize_level2_source(result["level2_auto"])
    _finalize_level2_source(result["level2_manual"])

    failed_layers = []
    check_level1 = run_layer in ("all", "level1")
    check_level2 = run_layer in ("all", "level2")

    if check_level1 and result["level1"]["status"] == "failed":
        failed_layers.append("level1")
    if check_level2 and result["level2_auto"]["status"] == "failed":
        failed_layers.append("level2_auto")
    if check_level2 and result["level2_manual"]["status"] == "failed":
        failed_layers.append("level2_manual")

    if failed_layers:
        result["status"] = "failed"
        result["reason"] = "layer_assertion_failed:" + ",".join(failed_layers)
    else:
        result["status"] = "passed"
        result["reason"] = "ok"

    return result


def _write_report(results: list[dict], report_path: Path, version):
    def _avg_metric(layer_name: str, metric_name: str):
        values = [
            r[layer_name][metric_name]
            for r in results
            if r["status"] != "skipped" and r[layer_name].get("asserted", False)
        ]
        if not values:
            return "n/a"
        return f"{(sum(values) / len(values)):.4f}"

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    active_total = sum(1 for r in results if r["status"] != "skipped")
    level1_asserted_count = sum(1 for r in results if r["status"] != "skipped" and r["level1"].get("asserted", False))
    level2_auto_asserted_count = sum(
        1 for r in results if r["status"] != "skipped" and r["level2_auto"].get("asserted", False)
    )
    level2_manual_asserted_count = sum(
        1 for r in results if r["status"] != "skipped" and r["level2_manual"].get("asserted", False)
    )

    level1_fail_count = sum(1 for r in results if r["status"] != "skipped" and r["level1"]["status"] == "failed")
    level1_pass_count = sum(1 for r in results if r["status"] != "skipped" and r["level1"]["status"] == "passed")
    level1_count_asserted_cases = [
        r for r in results if r["status"] != "skipped" and r["level1"].get("count_asserted", False)
    ]
    level1_count_fail_count = sum(1 for r in level1_count_asserted_cases if r["level1"].get("count_status") == "failed")
    level1_count_pass_count = sum(1 for r in level1_count_asserted_cases if r["level1"].get("count_status") == "passed")
    if level1_count_asserted_cases:
        level1_count_avg_f1 = f"{(sum(r['level1'].get('count_f1', 0.0) for r in level1_count_asserted_cases) / len(level1_count_asserted_cases)):.4f}"
    else:
        level1_count_avg_f1 = "n/a"
    level2_auto_fail_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_auto"]["status"] == "failed"
    )
    level2_auto_pass_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_auto"]["status"] == "passed"
    )
    level2_auto_not_asserted_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_auto"]["status"] == "not_asserted"
    )
    level2_manual_fail_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_manual"]["status"] == "failed"
    )
    level2_manual_pass_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_manual"]["status"] == "passed"
    )
    level2_manual_not_asserted_count = sum(
        1
        for r in results
        if r["status"] != "skipped" and r["level2_manual"]["status"] == "not_asserted"
    )
    level3_info_count = total

    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = []
    lines.append("# Tool2 Matching Layered Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append(f"- Dataset version: {version}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total: {total}")
    lines.append(f"- passed: {passed}")
    lines.append(f"- failed: {failed}")
    lines.append(f"- skipped: {skipped}")
    lines.append(f"- active_cases: {active_total}")
    lines.append(f"- level1_asserted_cases: {level1_asserted_count}/{active_total}")
    lines.append(f"- level2_auto_asserted_cases: {level2_auto_asserted_count}/{active_total}")
    lines.append(f"- level2_manual_asserted_cases: {level2_manual_asserted_count}/{active_total}")
    lines.append(f"- level1_pass_count: {level1_pass_count}")
    lines.append(f"- level1_fail_count: {level1_fail_count}")
    lines.append(f"- level1_avg_f1: {_avg_metric('level1', 'f1')}")
    lines.append(f"- level1_count_asserted_count: {len(level1_count_asserted_cases)}")
    lines.append(f"- level1_count_pass_count: {level1_count_pass_count}")
    lines.append(f"- level1_count_fail_count: {level1_count_fail_count}")
    lines.append(f"- level1_count_avg_f1: {level1_count_avg_f1}")
    lines.append(f"- level2_auto_pass_count: {level2_auto_pass_count}")
    lines.append(f"- level2_auto_fail_count: {level2_auto_fail_count}")
    lines.append(f"- level2_auto_not_asserted_count: {level2_auto_not_asserted_count}")
    lines.append(f"- level2_auto_avg_f1: {_avg_metric('level2_auto', 'f1')}")
    lines.append(f"- level2_manual_pass_count: {level2_manual_pass_count}")
    lines.append(f"- level2_manual_fail_count: {level2_manual_fail_count}")
    lines.append(f"- level2_manual_not_asserted_count: {level2_manual_not_asserted_count}")
    lines.append(f"- level2_manual_avg_f1: {_avg_metric('level2_manual', 'f1')}")
    lines.append(f"- level3_info_count: {level3_info_count}")
    lines.append("")

    lines.append("## Per-Case Layer Status")
    lines.append("")
    for case in results:
        if case["status"] == "skipped":
            lines.append(f"- {case['id']} {case['name']}: skipped ({case['reason']})")
            continue
        l1 = case["level1"]
        l2_auto = case["level2_auto"]
        l2_manual = case["level2_manual"]
        l1_sim = _fmt_score(l1.get("f1"), bool(l1.get("asserted", False)))
        l1_count_sim = _fmt_score(l1.get("count_f1"), bool(l1.get("count_asserted", False)))
        l2_auto_sim = _fmt_score(l2_auto.get("f1"), bool(l2_auto.get("asserted", False)))
        l2_manual_sim = _fmt_score(l2_manual.get("f1"), bool(l2_manual.get("asserted", False)))
        lines.append(
            f"- {case['id']} {case['name']} | overall={case['status']} | "
            f"L1={l1['status']} (e={l1['expected_count']}, a={l1['actual_count']}, "
            f"sim={l1_sim}, count={l1.get('count_status', 'not_asserted')}:{l1_count_sim}) | "
            f"L2-auto={l2_auto['status']} (e={l2_auto['expected_count']}, a={l2_auto['actual_count']}, "
            f"sim={l2_auto_sim}) | "
            f"L2-manual={l2_manual['status']} (e={l2_manual['expected_count']}, a={l2_manual['actual_count']}, "
            f"sim={l2_manual_sim})"
        )
    lines.append("")

    failures = [r for r in results if r["status"] == "failed"]
    lines.append("## Failures")
    lines.append("")
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for case in failures:
            lines.append(f"### {case['id']} {case['name']}")
            lines.append("")
            lines.append(f"- file: {case['file']}")
            lines.append(f"- reason: {case['reason']}")
            lines.append(f"- used_mode: {case['used_mode']}")
            lines.append(f"- used_fallback: {case['used_fallback']}")
            lines.append(f"- reference_heading_found: {case['reference_heading_found']}")
            lines.append(f"- text_preview: {case['text_preview']}")
            lines.append(f"- citation_raw_preview: {case['citation_raw_preview']}")
            lines.append(f"- reference_raw_preview: {case['reference_raw_preview']}")
            lines.append("- level1_metrics:")
            lines.append(f"  - status: {case['level1']['status']}")
            lines.append(f"  - count(expected/actual/overlap): {case['level1']['expected_count']}/{case['level1']['actual_count']}/{case['level1']['overlap_count']}")
            lines.append(f"  - similarity(precision/recall/f1/jaccard): {case['level1']['precision']:.4f}/{case['level1']['recall']:.4f}/{case['level1']['f1']:.4f}/{case['level1']['jaccard']:.4f}")
            lines.append(f"  - count_asserted: {case['level1'].get('count_asserted', False)}")
            lines.append(f"  - count_status: {case['level1'].get('count_status', 'not_asserted')}")
            lines.append(
                f"  - count(expected/actual/overlap): {case['level1'].get('count_expected_total', 0)}/{case['level1'].get('count_actual_total', 0)}/{case['level1'].get('count_overlap_total', 0)}"
            )
            lines.append(
                f"  - count_similarity(precision/recall/f1): {case['level1'].get('count_precision', 1.0):.4f}/{case['level1'].get('count_recall', 1.0):.4f}/{case['level1'].get('count_f1', 1.0):.4f}"
            )
            lines.append("- level2_auto_metrics:")
            lines.append(f"  - status: {case['level2_auto']['status']}")
            lines.append(f"  - count(expected/actual/overlap): {case['level2_auto']['expected_count']}/{case['level2_auto']['actual_count']}/{case['level2_auto']['overlap_count']}")
            lines.append(f"  - similarity(precision/recall/f1/jaccard): {case['level2_auto']['precision']:.4f}/{case['level2_auto']['recall']:.4f}/{case['level2_auto']['f1']:.4f}/{case['level2_auto']['jaccard']:.4f}")
            lines.append("- level2_manual_metrics:")
            lines.append(f"  - status: {case['level2_manual']['status']}")
            lines.append(f"  - count(expected/actual/overlap): {case['level2_manual']['expected_count']}/{case['level2_manual']['actual_count']}/{case['level2_manual']['overlap_count']}")
            lines.append(f"  - similarity(precision/recall/f1/jaccard): {case['level2_manual']['precision']:.4f}/{case['level2_manual']['recall']:.4f}/{case['level2_manual']['f1']:.4f}/{case['level2_manual']['jaccard']:.4f}")
            lines.append("- level1:")
            lines.append("```json")
            lines.append(json.dumps(case["level1"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- level2_auto:")
            lines.append("```json")
            lines.append(json.dumps(case["level2_auto"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- level2_manual:")
            lines.append("```json")
            lines.append(json.dumps(case["level2_manual"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- level3_info:")
            lines.append("```json")
            lines.append(json.dumps(case["level3_info"], ensure_ascii=False, indent=2))
            lines.append("```")
            if case.get("warnings"):
                lines.append("- warnings:")
                lines.append("```json")
                lines.append(json.dumps(case["warnings"], ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")

    lines.append("## Not Asserted")
    lines.append("")
    not_asserted_cases = [
        r for r in results if r["status"] != "skipped" and (not r["level2_auto"]["asserted"] or not r["level2_manual"]["asserted"])
    ]
    if not not_asserted_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in not_asserted_cases:
            flags = []
            if not case["level2_auto"]["asserted"]:
                flags.append("level2_auto")
            if not case["level2_manual"]["asserted"]:
                flags.append("level2_manual")
            lines.append(f"- {case['id']} {case['name']}: not_asserted={','.join(flags)}")
        lines.append("")

    lines.append("## Level3 Informational")
    lines.append("")
    for case in results:
        if case["status"] == "skipped":
            continue
        lines.append(
            f"- {case['id']} {case['name']}: matched={case['level3_info']['matched_count']}, "
            f"missing={case['level3_info']['missing_count']}, uncited={case['level3_info']['uncited_count']}"
        )
    lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_level1_report(results: list[dict], report_path: Path, version):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    total = len(results)
    skipped = sum(1 for r in results if r["status"] == "skipped")
    active_total = sum(1 for r in results if r["status"] != "skipped")
    asserted = [r for r in results if r["status"] != "skipped" and r["level1"].get("asserted", False)]
    passed = sum(1 for r in asserted if r["level1"]["status"] == "passed")
    failed = sum(1 for r in asserted if r["level1"]["status"] == "failed")
    avg_f1 = (sum(r["level1"]["f1"] for r in asserted) / len(asserted)) if asserted else 0.0
    count_asserted = [r for r in asserted if r["level1"].get("count_asserted", False)]
    count_passed = sum(1 for r in count_asserted if r["level1"].get("count_status") == "passed")
    count_failed = sum(1 for r in count_asserted if r["level1"].get("count_status") == "failed")
    count_avg_f1 = (sum(r["level1"].get("count_f1", 0.0) for r in count_asserted) / len(count_asserted)) if count_asserted else 0.0

    lines = []
    lines.append("# Tool2 Matching Level1 Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append(f"- Dataset version: {version}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total_cases: {total}")
    lines.append(f"- asserted_cases: {len(asserted)}")
    lines.append(f"- asserted_coverage: {len(asserted)}/{active_total}")
    lines.append(f"- passed: {passed}")
    lines.append(f"- failed: {failed}")
    lines.append(f"- skipped: {skipped}")
    lines.append(f"- avg_f1: {avg_f1:.4f}")
    lines.append(f"- count_asserted_cases: {len(count_asserted)}")
    lines.append(f"- count_passed: {count_passed}")
    lines.append(f"- count_failed: {count_failed}")
    lines.append(f"- count_avg_f1: {count_avg_f1:.4f}")
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    for case in results:
        if case["status"] == "skipped":
            lines.append(f"- {case['id']} {case['name']}: skipped ({case['reason']})")
            continue
        l1 = case["level1"]
        l1_f1 = _fmt_score(l1.get("f1"), bool(l1.get("asserted", False)))
        l1_count_f1 = _fmt_score(l1.get("count_f1"), bool(l1.get("count_asserted", False)))
        lines.append(
            f"- {case['id']} {case['name']}: {l1['status']} | "
            f"count(e/a/o)={l1['expected_count']}/{l1['actual_count']}/{l1['overlap_count']} | "
            f"sim(p/r/f1/j)={l1['precision']:.4f}/{l1['recall']:.4f}/{l1_f1}/{l1['jaccard']:.4f} | "
            f"count_assert={l1.get('count_asserted', False)} "
            f"count(e/a/o)={l1.get('count_expected_total', 0)}/{l1.get('count_actual_total', 0)}/{l1.get('count_overlap_total', 0)} "
            f"count_sim(p/r/f1)={l1.get('count_precision', 1.0):.4f}/{l1.get('count_recall', 1.0):.4f}/{l1_count_f1}"
        )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failed_cases = [r for r in asserted if r["level1"]["status"] == "failed"]
    if not failed_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in failed_cases:
            l1 = case["level1"]
            lines.append(f"### {case['id']} {case['name']}")
            lines.append("")
            lines.append(f"- file: {case['file']}")
            lines.append(f"- count(expected/actual/overlap): {l1['expected_count']}/{l1['actual_count']}/{l1['overlap_count']}")
            lines.append(f"- similarity(precision/recall/f1/jaccard): {l1['precision']:.4f}/{l1['recall']:.4f}/{l1['f1']:.4f}/{l1['jaccard']:.4f}")
            lines.append(f"- count_asserted: {l1.get('count_asserted', False)}")
            lines.append(f"- count_status: {l1.get('count_status', 'not_asserted')}")
            lines.append(
                f"- count(expected/actual/overlap): {l1.get('count_expected_total', 0)}/{l1.get('count_actual_total', 0)}/{l1.get('count_overlap_total', 0)}"
            )
            lines.append(
                f"- count_similarity(precision/recall/f1): {l1.get('count_precision', 1.0):.4f}/{l1.get('count_recall', 1.0):.4f}/{l1.get('count_f1', 1.0):.4f}"
            )
            lines.append("- expected_keys:")
            lines.append("```json")
            lines.append(json.dumps(l1["expected_keys"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- actual_keys:")
            lines.append("```json")
            lines.append(json.dumps(l1["actual_keys"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- expected_key_counts:")
            lines.append("```json")
            lines.append(json.dumps(l1.get("expected_key_counts", {}), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- actual_key_counts:")
            lines.append("```json")
            lines.append(json.dumps(l1.get("actual_key_counts", {}), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- count_mismatch_keys:")
            lines.append("```json")
            lines.append(json.dumps(l1.get("count_mismatch_keys", {}), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append(f"- citation_raw_preview: {case.get('citation_raw_preview', '')}")
            lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_level2_report(results: list[dict], report_path: Path, version):
    def _avg_from_asserted(cases: list[dict], value_getter):
        vals = [value_getter(c) for c in cases]
        if not vals:
            return None
        return sum(vals) / len(vals)

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    total = len(results)
    skipped = sum(1 for r in results if r["status"] == "skipped")
    active_total = sum(1 for r in results if r["status"] != "skipped")
    auto_asserted = [r for r in results if r["status"] != "skipped" and r["level2_auto"].get("asserted", False)]
    manual_asserted = [r for r in results if r["status"] != "skipped" and r["level2_manual"].get("asserted", False)]
    auto_avg_f1 = _mean_or_none([r["level2_auto"]["f1"] for r in auto_asserted])
    manual_avg_f1 = _mean_or_none([r["level2_manual"]["f1"] for r in manual_asserted])

    lines = []
    lines.append("# Tool2 Matching Level2 Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append(f"- Dataset version: {version}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total_cases: {total}")
    lines.append(f"- skipped: {skipped}")
    lines.append(f"- active_cases: {active_total}")
    lines.append(f"- auto_asserted_cases: {len(auto_asserted)}")
    lines.append(f"- auto_asserted_coverage: {len(auto_asserted)}/{active_total}")
    lines.append(f"- auto_passed: {sum(1 for r in auto_asserted if r['level2_auto']['status'] == 'passed')}")
    lines.append(f"- auto_failed: {sum(1 for r in auto_asserted if r['level2_auto']['status'] == 'failed')}")
    lines.append(f"- auto_avg_f1: {_fmt_score(auto_avg_f1)}")
    lines.append(f"- manual_asserted_cases: {len(manual_asserted)}")
    lines.append(f"- manual_asserted_coverage: {len(manual_asserted)}/{active_total}")
    lines.append(f"- manual_passed: {sum(1 for r in manual_asserted if r['level2_manual']['status'] == 'passed')}")
    lines.append(f"- manual_failed: {sum(1 for r in manual_asserted if r['level2_manual']['status'] == 'failed')}")
    lines.append(f"- manual_avg_f1: {_fmt_score(manual_avg_f1)}")
    auto_pos_asserted = [r for r in auto_asserted if r["level2_auto"]["position"]["asserted"]]
    manual_pos_asserted = [r for r in manual_asserted if r["level2_manual"]["position"]["asserted"]]
    auto_parse_asserted = [r for r in auto_asserted if r["level2_auto"]["parsed_fields"]["asserted"]]
    manual_parse_asserted = [r for r in manual_asserted if r["level2_manual"]["parsed_fields"]["asserted"]]
    lines.append(f"- auto_position_asserted_cases: {len(auto_pos_asserted)}")
    lines.append(
        f"- auto_position_avg_f1: {_fmt_score(_avg_from_asserted(auto_pos_asserted, lambda x: x['level2_auto']['position']['f1']))}"
    )
    lines.append(f"- auto_parsed_asserted_cases: {len(auto_parse_asserted)}")
    lines.append(
        f"- auto_parsed_avg_field_accuracy: {_fmt_score(_avg_from_asserted(auto_parse_asserted, lambda x: x['level2_auto']['parsed_fields']['field_accuracy']))}"
    )
    lines.append(f"- manual_position_asserted_cases: {len(manual_pos_asserted)}")
    lines.append(
        f"- manual_position_avg_f1: {_fmt_score(_avg_from_asserted(manual_pos_asserted, lambda x: x['level2_manual']['position']['f1']))}"
    )
    lines.append(f"- manual_parsed_asserted_cases: {len(manual_parse_asserted)}")
    lines.append(
        f"- manual_parsed_avg_field_accuracy: {_fmt_score(_avg_from_asserted(manual_parse_asserted, lambda x: x['level2_manual']['parsed_fields']['field_accuracy']))}"
    )
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    for case in results:
        if case["status"] == "skipped":
            lines.append(f"- {case['id']} {case['name']}: skipped ({case['reason']})")
            continue
        a = case["level2_auto"]
        m = case["level2_manual"]
        a_key_p = _fmt_score(a.get("precision"), bool(a.get("asserted", False)))
        a_key_r = _fmt_score(a.get("recall"), bool(a.get("asserted", False)))
        a_key = _fmt_score(a.get("f1"), bool(a.get("asserted", False)))
        a_pos = _fmt_score(a["position"].get("f1"), bool(a["position"].get("asserted", False)))
        a_parse = _fmt_score(a["parsed_fields"].get("field_accuracy"), bool(a["parsed_fields"].get("asserted", False)))
        m_key_p = _fmt_score(m.get("precision"), bool(m.get("asserted", False)))
        m_key_r = _fmt_score(m.get("recall"), bool(m.get("asserted", False)))
        m_key = _fmt_score(m.get("f1"), bool(m.get("asserted", False)))
        m_pos = _fmt_score(m["position"].get("f1"), bool(m["position"].get("asserted", False)))
        m_parse = _fmt_score(m["parsed_fields"].get("field_accuracy"), bool(m["parsed_fields"].get("asserted", False)))
        lines.append(
            f"- {case['id']} {case['name']} | "
            f"auto={a['status']} key(p/r/f1)={a_key_p}/{a_key_r}/{a_key} "
            f"pos={a['position']['status']}({a['position']['matched_count']}/{a['position']['expected_count']},f1={a_pos}) "
            f"parse={a['parsed_fields']['status']}(fields={a['parsed_fields']['matched_fields']}/{a['parsed_fields']['expected_fields']},acc={a_parse}) "
            f"coverage(source)={a['parse_coverage'].get('source_detected_count', 0)}/{a['parse_coverage']['total_items']} | "
            f"manual={m['status']} key(p/r/f1)={m_key_p}/{m_key_r}/{m_key} "
            f"pos={m['position']['status']}({m['position']['matched_count']}/{m['position']['expected_count']},f1={m_pos}) "
            f"parse={m['parsed_fields']['status']}(fields={m['parsed_fields']['matched_fields']}/{m['parsed_fields']['expected_fields']},acc={m_parse}) "
            f"coverage(source)={m['parse_coverage'].get('source_detected_count', 0)}/{m['parse_coverage']['total_items']}"
        )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failed_cases = [
        r
        for r in results
        if r["status"] != "skipped" and (r["level2_auto"]["status"] == "failed" or r["level2_manual"]["status"] == "failed")
    ]
    if not failed_cases:
        lines.append("None")
        lines.append("")
    else:
        for case in failed_cases:
            lines.append(f"### {case['id']} {case['name']}")
            lines.append("")
            lines.append(f"- file: {case['file']}")
            lines.append("- level2_auto:")
            lines.append("```json")
            lines.append(json.dumps(case["level2_auto"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("- level2_manual:")
            lines.append("```json")
            lines.append(json.dumps(case["level2_manual"], ensure_ascii=False, indent=2))
            lines.append("```")
            if case.get("warnings"):
                lines.append("- warnings:")
                lines.append("```json")
                lines.append(json.dumps(case["warnings"], ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_level3_report(results: list[dict], report_path: Path, version):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    total = len(results)
    skipped = sum(1 for r in results if r["status"] == "skipped")
    active = [r for r in results if r["status"] != "skipped"]

    lines = []
    lines.append("# Tool2 Matching Level3 Report (Informational)")
    lines.append("")
    lines.append(f"- Generated at (ISO): {now}")
    lines.append(f"- Dataset version: {version}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total_cases: {total}")
    lines.append(f"- skipped: {skipped}")
    lines.append(f"- informational_cases: {len(active)}")
    lines.append(f"- total_matched: {sum(r['level3_info']['matched_count'] for r in active)}")
    lines.append(f"- total_missing: {sum(r['level3_info']['missing_count'] for r in active)}")
    lines.append(f"- total_uncited: {sum(r['level3_info']['uncited_count'] for r in active)}")
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    for case in results:
        if case["status"] == "skipped":
            lines.append(f"- {case['id']} {case['name']}: skipped ({case['reason']})")
            continue
        info = case["level3_info"]
        lines.append(
            f"- {case['id']} {case['name']}: "
            f"matched={info['matched_count']}, missing={info['missing_count']}, uncited={info['uncited_count']}"
        )
    lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _load_layer_expected(path: Path, label: str, expected_version: int | None = None) -> tuple[dict, list[str]]:
    warnings = []
    if not path.exists():
        warnings.append(f"{label}: expected file not found ({path})")
        return {}, warnings

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        warnings.append(f"{label}: failed to parse expected file ({e})")
        return {}, warnings

    if not isinstance(payload, dict):
        warnings.append(f"{label}: invalid expected format (must be object)")
        return {}, warnings
    payload_version = payload.get("version")
    if expected_version is not None and payload_version != expected_version:
        warnings.append(f"{label}: expected file version={expected_version}, got {payload_version}")

    cases_obj = payload.get("cases", {})
    out = {}
    if isinstance(cases_obj, dict):
        for case_id, value in cases_obj.items():
            if isinstance(value, dict):
                out[str(case_id)] = value
    elif isinstance(cases_obj, list):
        for row in cases_obj:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id", "")).strip()
            if not cid:
                continue
            out[cid] = row.get("expected", {}) if isinstance(row.get("expected", {}), dict) else {}
    else:
        warnings.append(f"{label}: invalid cases payload (must be object or list)")
    return out, warnings


def _merge_case_expected(case: dict, layer1_map: dict, layer2_map: dict, layer3_map: dict) -> dict:
    case_id = str(case.get("id", "")).strip()
    merged = {}
    inline_expected = case.get("expected", {})
    if isinstance(inline_expected, dict):
        merged.update(inline_expected)
    if case_id in layer1_map and isinstance(layer1_map[case_id], dict):
        merged.update(layer1_map[case_id])
    if case_id in layer2_map and isinstance(layer2_map[case_id], dict):
        merged.update(layer2_map[case_id])
    if case_id in layer3_map and isinstance(layer3_map[case_id], dict):
        merged.update(layer3_map[case_id])
    return merged


def _print_old_schema_error() -> None:
    print("[ERROR] matching_cases.json is still old schema (text/references/expected-matching list).")
    print("Please migrate to version=2 document schema used by Tool2 layered tests.")
    print("Required shape:")
    print('{"version":2,"cases":[{"id":"t001","file":"xxx.docx","body_extract":{...},"references":[],"expected":{"level1_citation_keys":[...],"level2_auto_reference_keys":[...],"level2_manual_reference_keys":[...]}}]}')


def _level2_case_status(case: dict) -> str:
    if case.get("status") == "skipped":
        return "skipped"

    auto = case["level2_auto"]
    manual = case["level2_manual"]
    has_asserted = bool(auto.get("asserted")) or bool(manual.get("asserted"))

    if not has_asserted:
        return "not_asserted"
    if auto.get("status") == "failed" or manual.get("status") == "failed":
        return "failed"
    return "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Tool2 layered matching tests")
    parser.add_argument(
        "--layer",
        choices=["all", "level1", "level2", "level3"],
        default="all",
        help="run mode: all layers or a single layer",
    )
    args = parser.parse_args()

    if not CASES_PATH.exists():
        print(f"Cases file not found: {CASES_PATH}")
        return 1

    try:
        payload = json.loads(CASES_PATH.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"Failed to read matching cases JSON: {e}")
        return 1

    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "text" in payload[0] and "references" in payload[0]:
            _print_old_schema_error()
            return 1
        print("Invalid cases format: expected object with version and cases")
        return 1

    if not isinstance(payload, dict):
        print("Invalid cases format: expected object with version and cases")
        return 1

    version = payload.get("version")
    cases = payload.get("cases")
    if version != 2:
        print(f"[WARN] expected matching dataset version=2, got {version}")

    if not isinstance(cases, list):
        print("Invalid cases format: 'cases' must be a list")
        return 1

    level1_map, level1_warnings = _load_layer_expected(LEVEL1_EXPECTED_PATH, "level1", expected_version=2)
    level2_map, level2_warnings = _load_layer_expected(LEVEL2_EXPECTED_PATH, "level2", expected_version=2)
    level3_map, level3_warnings = _load_layer_expected(LEVEL3_EXPECTED_PATH, "level3", expected_version=2)
    for warn in [*level1_warnings, *level2_warnings, *level3_warnings]:
        print(f"[WARN] {warn}")

    results = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        merged_expected = _merge_case_expected(case, level1_map, level2_map, level3_map)
        result = _run_case(case, merged_expected, run_layer=args.layer)
        results.append(result)
        print(
            f"[{result['status'].upper()}] {result['id']} {result['name']} ({result['file']}) "
            f"| L1={result['level1']['status']} "
            f"| L2-auto={result['level2_auto']['status']} "
            f"| L2-manual={result['level2_manual']['status']}"
        )
        for warning in result.get("warnings", []):
            print(f"  [WARN] {warning}")

    if args.layer == "all":
        _write_report(results, REPORT_PATH, version)
        _write_level1_report(results, REPORT_LEVEL1_PATH, version)
        _write_level2_report(results, REPORT_LEVEL2_PATH, version)
        _write_level3_report(results, REPORT_LEVEL3_PATH, version)
    elif args.layer == "level1":
        _write_level1_report(results, REPORT_LEVEL1_PATH, version)
    elif args.layer == "level2":
        _write_level2_report(results, REPORT_LEVEL2_PATH, version)
    else:
        _write_level3_report(results, REPORT_LEVEL3_PATH, version)

    total = len(results)
    skipped = sum(1 for r in results if r["status"] == "skipped")

    if args.layer == "all":
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        not_asserted = 0
    elif args.layer == "level1":
        asserted = [r for r in results if r["status"] != "skipped" and r["level1"].get("asserted", False)]
        passed = sum(1 for r in asserted if r["level1"]["status"] == "passed")
        failed = sum(1 for r in asserted if r["level1"]["status"] == "failed")
        not_asserted = sum(1 for r in results if r["status"] != "skipped" and not r["level1"].get("asserted", False))
    elif args.layer == "level2":
        layer2_statuses = [_level2_case_status(r) for r in results]
        passed = sum(1 for s in layer2_statuses if s == "passed")
        failed = sum(1 for s in layer2_statuses if s == "failed")
        not_asserted = sum(1 for s in layer2_statuses if s == "not_asserted")
    else:
        passed = sum(1 for r in results if r["status"] != "skipped")
        failed = 0
        not_asserted = 0

    print("---")
    print(f"Mode: {args.layer}")
    print(f"Total: {total}")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"SKIPPED: {skipped}")
    if not_asserted:
        print(f"NOT_ASSERTED: {not_asserted}")

    if args.layer == "all":
        print(f"Report written: {REPORT_PATH}")
        print(f"Level1 report: {REPORT_LEVEL1_PATH}")
        print(f"Level2 report: {REPORT_LEVEL2_PATH}")
        print(f"Level3 report: {REPORT_LEVEL3_PATH}")
    elif args.layer == "level1":
        print(f"Report written: {REPORT_LEVEL1_PATH}")
    elif args.layer == "level2":
        print(f"Report written: {REPORT_LEVEL2_PATH}")
    else:
        print(f"Report written: {REPORT_LEVEL3_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
