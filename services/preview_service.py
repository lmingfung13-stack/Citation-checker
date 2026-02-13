import hashlib
from collections import OrderedDict
from threading import Lock

from PIL import Image
from utils.errors import PreviewError
from utils.logging_utils import get_logger, log_exception

try:
    import fitz  # PyMuPDF, need `pip install pymupdf`
except ImportError:
    fitz = None

_PREVIEW_CACHE_CAP = 30
_PREVIEW_CACHE = OrderedDict()
_PREVIEW_CACHE_LOCK = Lock()
_LOGGER = get_logger("preview_service")


def _build_preview_cache_key(pdf_bytes: bytes, page_num: int, highlight_text: str):
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    if highlight_text:
        highlight_hash = hashlib.sha256(highlight_text.encode("utf-8", errors="ignore")).hexdigest()
    else:
        highlight_hash = ""
    return pdf_hash, page_num, highlight_hash


def _get_cached_preview(key):
    with _PREVIEW_CACHE_LOCK:
        cached = _PREVIEW_CACHE.get(key)
        if cached is None:
            return None
        _PREVIEW_CACHE.move_to_end(key)
        return cached.copy()


def _set_cached_preview(key, img):
    with _PREVIEW_CACHE_LOCK:
        _PREVIEW_CACHE[key] = img.copy()
        _PREVIEW_CACHE.move_to_end(key)
        while len(_PREVIEW_CACHE) > _PREVIEW_CACHE_CAP:
            _PREVIEW_CACHE.popitem(last=False)


def _log_preview_error(context: str, message: str, detail: str | None = None, cause: Exception | None = None):
    app_err = PreviewError(message=message, detail=detail, cause=cause)
    log_exception(context, app_err, _LOGGER)


def get_pdf_page_image(pdf_bytes: bytes, page_num: int, highlight_text: str = None):
    if fitz is None:
        _log_preview_error("preview.missing_fitz", "Preview dependency is unavailable.", "PyMuPDF (fitz) import failed.")
        return None

    try:
        p_num = int(page_num)
    except Exception as e:
        _log_preview_error("preview.invalid_page_num", "Failed to render preview.", f"Invalid page number: {page_num}", e)
        return None

    clean_search = ""
    if highlight_text:
        clean_search = highlight_text.replace("...", "").strip()

    cache_key = _build_preview_cache_key(pdf_bytes, p_num, clean_search)
    cached = _get_cached_preview(cache_key)
    if cached is not None:
        return cached

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        _log_preview_error("preview.open_pdf", "Failed to render preview.", "Failed to open PDF bytes with PyMuPDF.", e)
        return None

    p_idx = p_num - 1
    if p_idx < 0 or p_idx >= len(doc):
        try:
            doc.close()
        except Exception:
            pass
        _log_preview_error("preview.page_out_of_range", "Failed to render preview.", f"Page index out of range: {p_num}")
        return None

    try:
        page = doc[p_idx]
        rects = []

        if highlight_text:
            rects = page.search_for(clean_search)

            if not rects and len(clean_search) > 30:
                rects = page.search_for(clean_search[:30])
                if not rects:
                    rects = page.search_for(clean_search[:15])

            if not rects and len(clean_search) <= 30:
                no_parens = clean_search.replace("(", "").replace(")", "").replace("?", "").replace("?", "").strip()
                if no_parens != clean_search:
                    rects = page.search_for(no_parens)

                if not rects and "," in no_parens:
                    no_comma = no_parens.replace(",", "")
                    rects = page.search_for(no_comma)

            if rects:
                shape = page.new_shape()
                for r in rects:
                    shape.draw_rect(r)
                    shape.finish(color=(1, 0, 0), fill=(1, 1, 0), fill_opacity=0.4, width=2)
                shape.commit()

        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        _set_cached_preview(cache_key, img)
        return img.copy()
    except Exception as e:
        _log_preview_error("preview.render", "Failed to render preview.", "Unexpected preview rendering error.", e)
        return None
    finally:
        try:
            doc.close()
        except Exception:
            pass
