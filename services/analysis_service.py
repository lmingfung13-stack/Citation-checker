import hashlib
import os
from collections import OrderedDict
from threading import Lock

import pandas as pd

from citation_core import (
    DocParagraph,
    extract_intext_citations,
    extract_reference_items,
    find_reference_section_start,
    match_citations_to_refs,
    parse_reference_item as parse_citation_core_reference_item,
    read_docx_bytes,
    read_pdf_bytes,
)
from services.reference_service import split_reference_items
from utils.errors import ParseError, ReferenceSectionNotFoundError
from utils.logging_utils import get_logger, log_exception

_ANALYSIS_CACHE_CAP = 3
_ANALYSIS_CACHE = OrderedDict()
_ANALYSIS_CACHE_LOCK = Lock()
_LOGGER = get_logger("analysis_service")
ANALYSIS_ENGINE_VERSION = "2026-02-22-citation-filter-v1"

SUMMARY_COL_BODY_PARAGRAPHS = "正文段落數"
SUMMARY_COL_REFERENCE_ITEMS = "參考文獻項目數"
SUMMARY_COL_CITATIONS = "正文引用數"
SUMMARY_COL_MATCHED = "成功配對數"
SUMMARY_COL_MISSING = "缺失引用數（正文有/文末無）"
SUMMARY_COL_UNCITED = "未引用文獻數（文末有/正文無）"


def _build_analysis_cache_key(
    file_bytes: bytes,
    resolved_file_type: str,
    filename: str | None,
    override_signature: str = "auto",
):
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    filename_key = (filename or "").strip()
    return file_hash, resolved_file_type, filename_key, override_signature, ANALYSIS_ENGINE_VERSION


def _get_cached_analysis(key):
    with _ANALYSIS_CACHE_LOCK:
        cached = _ANALYSIS_CACHE.get(key)
        if cached is None:
            return None
        _ANALYSIS_CACHE.move_to_end(key)
        return cached


def _set_cached_analysis(key, value):
    with _ANALYSIS_CACHE_LOCK:
        _ANALYSIS_CACHE[key] = value
        _ANALYSIS_CACHE.move_to_end(key)
        while len(_ANALYSIS_CACHE) > _ANALYSIS_CACHE_CAP:
            _ANALYSIS_CACHE.popitem(last=False)


def _is_reference_section_not_found_message(message: str) -> bool:
    normalized = (message or "").strip().lower()
    keywords = (
        "reference",
        "bibliography",
        "heading",
        "section",
        "參考文獻",
        "参考文献",
        "文獻",
        "文献",
    )
    return any(k in normalized for k in keywords)


def _resolve_file_type(filename: str | None, file_type: str | None) -> str:
    resolved_file_type = (file_type or "").strip().lower()
    if not resolved_file_type and filename:
        resolved_file_type = os.path.splitext(filename)[1].lower().lstrip(".")
    return resolved_file_type


def _build_override_signature(
    override_reference_text: str | None,
    override_reference_items: list[str] | None,
) -> str:
    if override_reference_items is not None:
        compact_items = [str(item).strip() for item in override_reference_items if str(item).strip()]
        joined = "\n".join(compact_items)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        return f"items:{digest}"

    text = (override_reference_text or "").strip()
    if text:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"text:{digest}"

    return "auto"


def _read_paragraphs_from_bytes(file_bytes: bytes, resolved_file_type: str):
    if resolved_file_type == "docx":
        return read_docx_bytes(file_bytes)
    if resolved_file_type == "pdf":
        return read_pdf_bytes(file_bytes)
    raise ValueError("不支援的檔案類型，無法進行引用分析。")


def _build_override_reference_items(
    override_reference_text: str | None,
    override_reference_items: list[str] | None,
) -> list[str] | None:
    if override_reference_items is not None:
        if not isinstance(override_reference_items, list):
            raise ParseError(detail="覆蓋參考文獻必須是字串陣列。")
        cleaned = [str(item).strip() for item in override_reference_items if str(item).strip()]
        if not cleaned:
            raise ParseError(detail="覆蓋參考文獻清單為空。")
        return cleaned

    raw_text = (override_reference_text or "").strip()
    if not raw_text:
        return None

    try:
        items = split_reference_items(raw_text)
    except Exception as e:
        raise ParseError(
            detail="無法將覆蓋參考文獻文字切分為項目。",
            cause=e,
        ) from e

    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        raise ParseError(detail="覆蓋參考文獻文字無法產生任何有效項目。")
    return cleaned


def _parse_override_references(reference_items: list[str]):
    refs = []
    ref_paras_raw = []
    failed_items = []

    for idx, raw_item in enumerate(reference_items):
        item_text = str(raw_item).strip()
        if not item_text:
            continue
        ref_paras_raw.append(DocParagraph(item_text, 0))
        parsed = parse_citation_core_reference_item(item_text, idx, 0)
        if parsed is None:
            failed_items.append(item_text)
            continue
        refs.append(parsed)

    return refs, ref_paras_raw, failed_items


def _build_summary_df(body_count: int, ref_count: int, citation_count: int, matched_count: int, missing_count: int, uncited_count: int):
    return pd.DataFrame([
        {
            SUMMARY_COL_BODY_PARAGRAPHS: body_count,
            SUMMARY_COL_REFERENCE_ITEMS: ref_count,
            SUMMARY_COL_CITATIONS: citation_count,
            SUMMARY_COL_MATCHED: matched_count,
            SUMMARY_COL_MISSING: missing_count,
            SUMMARY_COL_UNCITED: uncited_count,
        }
    ])


def _run_single_matching_engine(
    file_bytes: bytes,
    resolved_file_type: str,
    override_reference_text: str | None = None,
    override_reference_items: list[str] | None = None,
):
    # Single source of truth: one matching engine, selectable reference source.
    paragraphs = _read_paragraphs_from_bytes(file_bytes, resolved_file_type)
    ref_start = find_reference_section_start(paragraphs)

    requested_override = override_reference_items is not None or bool((override_reference_text or "").strip())
    override_warning = None
    override_items_count = 0
    override_parse_failed_count = 0
    reference_source = "auto_extracted"

    if ref_start is None:
        if not requested_override:
            raise ValueError("找不到參考文獻章節標題。")
        body_paras = paragraphs
        ref_paras_raw = []
        refs = []
    else:
        body_paras = paragraphs[:ref_start]
        ref_paras_raw = paragraphs[ref_start:]
        refs = extract_reference_items(paragraphs, ref_start)

    if requested_override:
        try:
            override_items = _build_override_reference_items(override_reference_text, override_reference_items)
        except ParseError as e:
            override_warning = f"{e.message} 已回退為文件自動抽取文獻。"
            _LOGGER.warning("analysis.override.invalid fallback=auto detail=%s", e.detail or e.message)
            override_items = None

        if override_items:
            override_items_count = len(override_items)
            parsed_override_refs, override_ref_paras_raw, failed_items = _parse_override_references(override_items)
            override_parse_failed_count = len(failed_items)

            if parsed_override_refs:
                refs = parsed_override_refs
                ref_paras_raw = override_ref_paras_raw
                reference_source = "user_override"
                if failed_items:
                    override_warning = (
                        f"覆蓋參考文獻僅部分解析成功："
                        f"{len(parsed_override_refs)}/{len(override_items)} 筆。"
                    )
                    _LOGGER.warning(
                        "analysis.override.partial parsed=%s total=%s",
                        len(parsed_override_refs),
                        len(override_items),
                    )
            else:
                override_warning = "覆蓋參考文獻無法解析，已回退為文件自動抽取文獻。"
                _LOGGER.warning("analysis.override.parse_failed fallback=auto total=%s", len(override_items))

    citations = extract_intext_citations(body_paras, known_refs=refs)
    matched_df, missing_df, uncited_df = match_citations_to_refs(citations, refs, ref_paras_raw)
    summary_df = _build_summary_df(
        body_count=len(body_paras),
        ref_count=len(refs),
        citation_count=len(citations),
        matched_count=len(matched_df),
        missing_count=len(missing_df),
        uncited_count=len(uncited_df),
    )

    metadata = {
        "reference_source": reference_source,
        "reference_item_count": len(refs),
        "override_requested": requested_override,
        "override_items_count": override_items_count,
        "override_parse_failed_count": override_parse_failed_count,
        "warning": override_warning,
    }
    return (summary_df, matched_df, missing_df, uncited_df), metadata


def run_file_analysis(file_bytes: bytes, filename: str | None = None, file_type: str | None = None):
    result, _ = run_file_analysis_with_reference_override(
        file_bytes=file_bytes,
        filename=filename,
        file_type=file_type,
        override_reference_text=None,
        override_reference_items=None,
    )
    return result


def run_file_analysis_with_reference_override(
    file_bytes: bytes,
    filename: str | None = None,
    file_type: str | None = None,
    override_reference_text: str | None = None,
    override_reference_items: list[str] | None = None,
):
    """Run analysis once and optionally override reference source with user-provided items/text."""
    resolved_file_type = _resolve_file_type(filename, file_type)
    if not resolved_file_type:
        app_err = ParseError(detail="無法判斷檔案類型，無法進行引用分析。")
        log_exception("analysis.resolve_file_type", app_err, _LOGGER)
        raise app_err

    override_signature = _build_override_signature(override_reference_text, override_reference_items)
    cache_key = _build_analysis_cache_key(file_bytes, resolved_file_type, filename, override_signature)
    cached = _get_cached_analysis(cache_key)
    if cached is not None:
        return cached

    try:
        result_with_meta = _run_single_matching_engine(
            file_bytes=file_bytes,
            resolved_file_type=resolved_file_type,
            override_reference_text=override_reference_text,
            override_reference_items=override_reference_items,
        )
    except ValueError as e:
        msg = str(e)
        if _is_reference_section_not_found_message(msg):
            app_err = ReferenceSectionNotFoundError(message=msg, detail=msg, cause=e)
            log_exception("analysis.reference_section_not_found", app_err, _LOGGER)
            raise app_err from e
        app_err = ParseError(message=msg or None, detail=msg, cause=e)
        log_exception("analysis.value_error", app_err, _LOGGER)
        raise app_err from e
    except ParseError as e:
        log_exception("analysis.parse_error", e, _LOGGER)
        raise
    except Exception as e:
        app_err = ParseError(detail=str(e), cause=e)
        log_exception("analysis.unexpected_error", app_err, _LOGGER)
        raise app_err from e

    _set_cached_analysis(cache_key, result_with_meta)
    return result_with_meta
