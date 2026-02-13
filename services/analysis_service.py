import os
import hashlib
from collections import OrderedDict
from threading import Lock

from citation_core import run_check_from_file_bytes
from utils.errors import ParseError, ReferenceSectionNotFoundError
from utils.logging_utils import get_logger, log_exception

_ANALYSIS_CACHE_CAP = 3
_ANALYSIS_CACHE = OrderedDict()
_ANALYSIS_CACHE_LOCK = Lock()
_LOGGER = get_logger("analysis_service")


def _build_analysis_cache_key(file_bytes: bytes, resolved_file_type: str, filename: str | None):
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    filename_key = (filename or "").strip()
    return file_hash, resolved_file_type, filename_key


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
        "參考文獻",
        "reference",
        "bibliography",
        "heading",
        "section",
    )
    return any(k in normalized for k in keywords)


def run_file_analysis(file_bytes: bytes, filename: str | None = None, file_type: str | None = None):
    resolved_file_type = (file_type or "").strip().lower()
    if not resolved_file_type and filename:
        resolved_file_type = os.path.splitext(filename)[1].lower().lstrip(".")

    if not resolved_file_type:
        app_err = ParseError(detail="Unable to determine file type for citation analysis.")
        log_exception("analysis.resolve_file_type", app_err, _LOGGER)
        raise app_err

    cache_key = _build_analysis_cache_key(file_bytes, resolved_file_type, filename)
    cached = _get_cached_analysis(cache_key)
    if cached is not None:
        return cached

    try:
        result = run_check_from_file_bytes(file_bytes, resolved_file_type)
    except ValueError as e:
        msg = str(e)
        if _is_reference_section_not_found_message(msg):
            app_err = ReferenceSectionNotFoundError(message=msg, detail=msg, cause=e)
            log_exception("analysis.reference_section_not_found", app_err, _LOGGER)
            raise app_err from e
        app_err = ParseError(message=msg or None, detail=msg, cause=e)
        log_exception("analysis.value_error", app_err, _LOGGER)
        raise app_err from e
    except Exception as e:
        app_err = ParseError(detail=str(e), cause=e)
        log_exception("analysis.unexpected_error", app_err, _LOGGER)
        raise app_err from e

    _set_cached_analysis(cache_key, result)
    return result
