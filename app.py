# -*- coding: utf-8 -*-

import io
import hashlib
import os
import sys
import re
import time
import shutil
import threading
import tempfile
import streamlit as st
from PIL import Image
from services.convert_service import DOCX2PDF_AVAILABLE
from services.preview_service import get_pdf_page_image
from services.reference_service import (
    safe_normalize_reference_text,
    split_reference_items,
)
from services.analysis_service import (
    ANALYSIS_ENGINE_VERSION,
    run_file_analysis_with_reference_override,
)
from services.export_service import build_excel_report_bytes
from utils.chinese_sort import load_stroke_map, chinese_stroke_sort_key
from utils.i18n import LANG_EN, LANG_ZH, localize_df_columns, t
from services.job_service import (
    JOB_STATUS_CANCELED,
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    cancel_job,
    get_job,
    get_latest_job_for_hash,
    submit_docx_to_pdf_job,
)
from utils.errors import AppError, ReferenceSectionNotFoundError

REFERENCE_MODE_TOOL1 = "tool1"
REFERENCE_MODE_AUTO = "auto"
LEGACY_REFERENCE_MODE_MAP = {
    "使用工具1整理後文獻列表提高準確度": REFERENCE_MODE_TOOL1,
    "使用文件自動抽取的文獻列表": REFERENCE_MODE_AUTO,
    "Use cleaned list from Tool 1 (higher accuracy)": REFERENCE_MODE_TOOL1,
    "Use auto-extracted references from document": REFERENCE_MODE_AUTO,
}


def _contains_cjk_unified_char(text: str) -> bool:
    return any(0x4E00 <= ord(ch) <= 0x9FFF for ch in (text or ""))


def _tool1_reference_sort_key(item: str, stroke_map: dict[str, int]) -> tuple:
    text = (item or "").strip()
    if not text:
        return (3, "")
    # 工具1排序：中文在前、英文在後。
    if _contains_cjk_unified_char(text):
        strokes, key_char, raw_text = chinese_stroke_sort_key(text, stroke_map)
        return (0, strokes, key_char, raw_text.lower())
    if re.match(r"^[A-Za-z]", text):
        return (1, text.lower())
    return (2, text.lower())


def _normalize_reference_mode(value: str | None) -> str:
    if value in (REFERENCE_MODE_TOOL1, REFERENCE_MODE_AUTO):
        return str(value)
    return LEGACY_REFERENCE_MODE_MAP.get(str(value or "").strip(), REFERENCE_MODE_TOOL1)

# Try to import PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF, need `pip install pymupdf`
except ImportError:
    fitz = None

_initial_lang = st.session_state.get("ui_language", LANG_ZH)
if _initial_lang not in (LANG_ZH, LANG_EN):
    _initial_lang = LANG_ZH
st.set_page_config(page_title=t(_initial_lang, "page_title"), layout="wide")

# ----------------------------------------------------------------
# 自定義 CSS 與 JavaScript (優化介面與隱藏不必要的元素)
# ----------------------------------------------------------------
st.markdown("""
<style>
    /* 強制讓上傳區塊變大並加上虛線邊框 */
    div[data-testid="stFileUploader"] section {
        padding: 60px 20px;
        background-color: #f8f9fa;
        border: 3px dashed #cccccc;
        border-radius: 15px;
        text-align: center;
        transition: all 0.2s ease-in-out;
    }

    /* 合併 Drag & Hover 樣式 */
    .drag-active,
    div[data-testid="stFileUploader"] section:hover {
        background-color: #e8f5e9 !important;
        border-color: #4CAF50 !important;
        transform: scale(1.01) !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;
        cursor: pointer;
    }

    div[data-testid="stFileUploader"] section > div {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    /* 隱藏 "Browse files" 按鈕 */
    div[data-testid="stFileUploader"] button {
        display: none !important;
    }
    
    div[data-testid="stFileUploader"] small {
        font-size: 0.9em;
        color: #666;
    }
    
    div[data-testid="stFileUploader"] section > * {
        pointer-events: none;
    }

    /* === 介面精簡優化 === */
    
    /* 隱藏右上角的 Deploy 按鈕與選單 */
    .stDeployButton, [data-testid="stToolbar"] {
        display: none !important;
    }
    
    /* 隱藏側邊欄展開按鈕 */
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    
    /* 隱藏 Footer */
    footer {
        display: none !important;
    }
    
    /* 調整頂部 Padding，讓內容更緊湊 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem; /* 底部留白，避免被浮動按鈕擋住 */
    }

    /* 右下角固定語言切換 */
    div.st-key-floating_language {
        position: fixed;
        right: 16px;
        bottom: 16px;
        width: 180px;
        z-index: 1000;
        padding: 8px 10px 6px 10px;
        border: 1px solid #d9d9d9;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
    }

    div.st-key-floating_language [data-testid="stWidgetLabel"] {
        margin-bottom: 0.2rem;
    }

    div.st-key-floating_language p {
        font-size: 0.85rem;
    }
</style>

<script>
(function() {
    function addDragListeners(element) {
        if (element.dataset.dragListener === "true") return;
        let dragCounter = 0;
        element.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            element.classList.add('drag-active');
        });
        element.addEventListener('dragover', (e) => {
            e.preventDefault();
        });
        element.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter === 0) {
                element.classList.remove('drag-active');
            }
        });
        element.addEventListener('drop', (e) => {
            dragCounter = 0;
            element.classList.remove('drag-active');
        });
        element.dataset.dragListener = "true";
    }

    const observer = new MutationObserver(() => {
        const uploaderSection = document.querySelector('div[data-testid="stFileUploader"] section');
        if (uploaderSection) {
            addDragListeners(uploaderSection);
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------
# 固定在右下角的結束程式按鈕
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# Helper: DOCX 轉 PDF
# ----------------------------------------------------------------
# ----------------------------------------------------------------
# Helper: PDF 視覺化 (嚴謹版：避免過度反黃)
# ----------------------------------------------------------------
# ----------------------------------------------------------------
# 主程式
# ----------------------------------------------------------------
if "ui_language" not in st.session_state:
    st.session_state.ui_language = LANG_ZH
if st.session_state.ui_language not in (LANG_ZH, LANG_EN):
    st.session_state.ui_language = LANG_ZH

if "file_bytes" not in st.session_state:
    st.session_state.file_bytes = None
if "file_type" not in st.session_state:
    st.session_state.file_type = None
if "check_results" not in st.session_state:
    st.session_state.check_results = None
if "analysis_meta" not in st.session_state:
    st.session_state.analysis_meta = None
if "last_processed_key" not in st.session_state:
    st.session_state.last_processed_key = None
if "docx_pdf_job_id" not in st.session_state:
    st.session_state.docx_pdf_job_id = None
if "docx_pdf_job_key" not in st.session_state:
    st.session_state.docx_pdf_job_key = None
if "docx_pdf_file_hash" not in st.session_state:
    st.session_state.docx_pdf_file_hash = None
if "ref_tool_formatted_text" not in st.session_state:
    st.session_state.ref_tool_formatted_text = None
if "ref_tool_report" not in st.session_state:
    st.session_state.ref_tool_report = None
if "ref_tool_clean_text" not in st.session_state:
    st.session_state.ref_tool_clean_text = None
if "ref_tool_raw_output" not in st.session_state:
    st.session_state.ref_tool_raw_output = None
if "ref_tool_sorted_output" not in st.session_state:
    st.session_state.ref_tool_sorted_output = None
if "use_clean_references_for_analysis" not in st.session_state:
    st.session_state.use_clean_references_for_analysis = True
if "reference_source_mode_ui" not in st.session_state:
    st.session_state.reference_source_mode_ui = REFERENCE_MODE_TOOL1
st.session_state.reference_source_mode_ui = _normalize_reference_mode(
    st.session_state.get("reference_source_mode_ui")
)

if "ui_language_widget" not in st.session_state:
    st.session_state.ui_language_widget = st.session_state.ui_language
if st.session_state.ui_language_widget not in (LANG_ZH, LANG_EN):
    st.session_state.ui_language_widget = LANG_ZH

with st.container(key="floating_language"):
    st.selectbox(
        "Language / 語言",
        options=[LANG_ZH, LANG_EN],
        format_func=lambda code: "中文" if code == LANG_ZH else "English",
        key="ui_language_widget",
    )

if st.session_state.ui_language != st.session_state.ui_language_widget:
    st.session_state.ui_language = st.session_state.ui_language_widget
lang = st.session_state.ui_language

st.title(t(lang, "app_title"))
st.warning(t(lang, "disclaimer"))

if fitz is None:
    st.error(t(lang, "error_missing_pymupdf"))

tool_page_tool1, tool_page_tool2 = st.tabs([t(lang, "tab_tool1"), t(lang, "tab_tool2")])

with tool_page_tool1:
    raw_ref_text = st.text_area(
        t(lang, "tool1_input_label"),
        key="ref_tool_raw_text",
        height=180,
    )
    if st.button(t(lang, "tool1_run_button"), key="ref_tool_run"):
        clean_text = safe_normalize_reference_text(raw_ref_text)
        raw_items = split_reference_items(raw_ref_text)
        clean_items = split_reference_items(clean_text)
        try:
            stroke_map = load_stroke_map()
        except Exception:
            stroke_map = {}
        sorted_clean_items = sorted(clean_items, key=lambda item: _tool1_reference_sort_key(item, stroke_map))
        final_clean_text = "\n".join(sorted_clean_items) if sorted_clean_items else clean_text.strip()

        st.session_state.ref_tool_raw_output = raw_ref_text
        st.session_state.ref_tool_clean_text = final_clean_text
        st.session_state.ref_tool_formatted_text = final_clean_text
        st.session_state.ref_tool_sorted_output = final_clean_text
        st.session_state.ref_tool_report = {
            "raw_items": len(raw_items),
            "clean_items": len(clean_items),
        }

    if st.session_state.ref_tool_clean_text is not None:
        report = st.session_state.ref_tool_report or {}
        st.caption(
            t(
                lang,
                "tool1_done_caption",
                raw_items=report.get("raw_items", 0),
                clean_items=report.get("clean_items", 0),
            )
        )
        st.text_area(
            t(lang, "tool1_result_label"),
            value=st.session_state.ref_tool_clean_text or "",
            height=260,
        )
        if st.session_state.ref_tool_clean_text:
            st.download_button(
                t(lang, "tool1_download_txt"),
                data=st.session_state.ref_tool_clean_text,
                file_name=t(lang, "tool1_download_filename"),
                mime="text/plain",
                key="ref_tool_download_txt",
            )
    else:
        st.info(t(lang, "tool1_empty_info"))


with tool_page_tool2:
    uploaded = st.file_uploader(t(lang, "uploader_label"), type=["docx", "pdf"])
    clean_reference_text = (st.session_state.get("ref_tool_clean_text") or "").strip()

    auto_switched_to_auto = (
        uploaded is not None
        and _normalize_reference_mode(st.session_state.get("reference_source_mode_ui")) == REFERENCE_MODE_TOOL1
        and not clean_reference_text
    )
    if auto_switched_to_auto:
        st.session_state.reference_source_mode_ui = REFERENCE_MODE_AUTO
        st.session_state.use_clean_references_for_analysis = False

    reference_source_mode = st.radio(
        t(lang, "reference_source_label"),
        options=[REFERENCE_MODE_TOOL1, REFERENCE_MODE_AUTO],
        format_func=lambda mode: t(lang, f"reference_source_{mode}"),
        horizontal=True,
        key="reference_source_mode_ui",
    )
    selected_reference_source_mode = _normalize_reference_mode(reference_source_mode)
    st.session_state.use_clean_references_for_analysis = (
        selected_reference_source_mode == REFERENCE_MODE_TOOL1
    )
    if auto_switched_to_auto:
        st.info(t(lang, "auto_switch_info"))

    if not uploaded:
        st.info(t(lang, "steps_info"))

    if uploaded:
        raw_bytes = uploaded.getvalue()
        raw_type = uploaded.name.split(".")[-1].lower()
        
        use_conversion = False
        
        status_container = st.container()
        metrics_container = st.container()
        st.markdown("---")
        col_left, col_right = st.columns([1.5, 1])

        with col_right:
            st.subheader(t(lang, "preview_title"))
            if fitz is None:
                st.error(t(lang, "preview_disabled_missing_pymupdf"))
            elif raw_type == "docx":
                if DOCX2PDF_AVAILABLE:
                    st.info(t(lang, "preview_text_mode_info"))
                    use_conversion = st.checkbox(t(lang, "preview_enable_docx_pdf"), value=False)
                    st.markdown("---")
                else:
                    st.caption(t(lang, "preview_docx_no_converter"))
                    st.markdown("---")

        use_reference_override = st.session_state.get("use_clean_references_for_analysis", True)
        if use_reference_override and not clean_reference_text:
            st.info(t(lang, "override_fallback_info"))
            use_reference_override = False

        override_reference_text = clean_reference_text if (clean_reference_text and use_reference_override) else None
        override_signature = (
            hashlib.sha256(override_reference_text.encode("utf-8")).hexdigest()
            if override_reference_text
            else "auto"
        )

        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        current_key = f"{uploaded.name}_{use_conversion}_{content_hash}_{override_signature}_{ANALYSIS_ENGINE_VERSION}"

        with status_container:
            conversion_pending = False

            if st.session_state.last_processed_key != current_key:
                st.session_state.filename = uploaded.name
                st.session_state.check_results = None
                st.session_state.analysis_meta = None
                st.session_state.last_processed_key = current_key

                if raw_type == "docx" and use_conversion:
                    st.session_state.docx_pdf_job_id = submit_docx_to_pdf_job(raw_bytes)
                    st.session_state.docx_pdf_job_key = current_key
                    st.session_state.docx_pdf_file_hash = content_hash
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                else:
                    st.session_state.docx_pdf_job_id = None
                    st.session_state.docx_pdf_job_key = None
                    st.session_state.docx_pdf_file_hash = None
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = raw_type

            if raw_type == "docx" and use_conversion:
                active_job_id = st.session_state.get("docx_pdf_job_id")
                if not active_job_id:
                    latest = get_latest_job_for_hash(content_hash)
                    if latest and latest.status in (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, JOB_STATUS_DONE):
                        active_job_id = latest.job_id
                        st.session_state.docx_pdf_job_id = active_job_id
                        st.session_state.docx_pdf_file_hash = content_hash

                job = get_job(active_job_id) if active_job_id else None

                if job is None:
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                    st.warning(t(lang, "conversion_job_expired"))
                    if st.button(t(lang, "conversion_resubmit"), key=f"retry_docx_pdf_{content_hash}"):
                        st.session_state.docx_pdf_job_id = submit_docx_to_pdf_job(raw_bytes)
                        st.session_state.docx_pdf_job_key = current_key
                        st.session_state.docx_pdf_file_hash = content_hash
                        try:
                            st.rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                        st.stop()
                elif job.status == JOB_STATUS_DONE and job.result_bytes:
                    if st.session_state.file_type != "pdf":
                        st.session_state.check_results = None
                        st.success(t(lang, "conversion_success"))
                    st.session_state.file_bytes = job.result_bytes
                    st.session_state.file_type = "pdf"
                elif job.status == JOB_STATUS_FAILED:
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                    st.error(t(lang, "conversion_failed"))
                elif job.status == JOB_STATUS_CANCELED:
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                    st.warning(t(lang, "conversion_canceled"))
                    if st.button(t(lang, "conversion_resubmit"), key=f"retry_canceled_docx_pdf_{content_hash}"):
                        st.session_state.docx_pdf_job_id = submit_docx_to_pdf_job(raw_bytes)
                        st.session_state.docx_pdf_job_key = current_key
                        st.session_state.docx_pdf_file_hash = content_hash
                        try:
                            st.rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                        st.stop()
                elif job.status == JOB_STATUS_QUEUED:
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                    st.info(t(lang, "conversion_queued"))
                    if st.button(t(lang, "conversion_cancel"), key=f"cancel_docx_pdf_{active_job_id}"):
                        cancel_job(active_job_id)
                        try:
                            st.rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                        st.stop()
                    conversion_pending = True
                elif job.status == JOB_STATUS_RUNNING:
                    st.session_state.file_bytes = raw_bytes
                    st.session_state.file_type = "docx"
                    st.info(t(lang, "conversion_running"))
                    if st.button(t(lang, "conversion_cancel"), key=f"cancel_docx_pdf_{active_job_id}"):
                        cancel_job(active_job_id)
                        try:
                            st.rerun()
                        except Exception:
                            try:
                                st.experimental_rerun()
                            except Exception:
                                pass
                        st.stop()
                    conversion_pending = True

            file_bytes = st.session_state.file_bytes
            file_type = st.session_state.file_type

            if conversion_pending:
                time.sleep(0.3)
                try:
                    st.rerun()
                except Exception:
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass
                st.stop()

            if st.session_state.check_results is None:
                try:
                    with st.spinner(t(lang, "analyzing")):
                        results, analysis_meta = run_file_analysis_with_reference_override(
                            file_bytes=file_bytes,
                            filename=st.session_state.filename,
                            file_type=file_type,
                            override_reference_text=override_reference_text,
                        )
                        st.session_state.check_results = results
                        st.session_state.analysis_meta = analysis_meta
                except ReferenceSectionNotFoundError as e:
                    st.error(t(lang, "analysis_error_reference_section"))
                    st.caption(t(lang, "error_detail_caption", detail=e.message))
                    st.stop()
                except AppError as e:
                    st.error(t(lang, "analysis_error_app", error=e.message))
                    st.stop()
                except Exception as e:
                    st.error(t(lang, "analysis_error", error=e))
                    st.stop()

        summary_df, matched_df, missing_df, uncited_df = st.session_state.check_results
        analysis_meta = st.session_state.get("analysis_meta") or {}
        display_matched_df = localize_df_columns(matched_df, "matched", lang)
        display_missing_df = localize_df_columns(missing_df, "missing", lang)
        display_uncited_df = localize_df_columns(uncited_df, "uncited", lang)

        with metrics_container:
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric(t(lang, "metric_matched"), len(matched_df))
            col_m2.metric(t(lang, "metric_missing"), len(missing_df), delta_color="inverse")
            col_m3.metric(t(lang, "metric_uncited"), len(uncited_df), delta_color="inverse")

            reference_source = analysis_meta.get("reference_source", "auto_extracted")
            reference_count = analysis_meta.get("reference_item_count", 0)
            if reference_source == "user_override":
                st.caption(t(lang, "source_caption_tool1", count=reference_count))
            else:
                st.caption(t(lang, "source_caption_auto", count=reference_count))

            warning_text = (analysis_meta.get("warning") or "").strip()
            if warning_text:
                st.warning(t(lang, "warning_with_detail", detail=warning_text))

        preview_img = None
        preview_caption = t(lang, "preview_default_hint")
        waiting_for_selection = True

        with col_left:
            tab1, tab2, tab3 = st.tabs([
                t(lang, "tab_missing", count=len(missing_df)),
                t(lang, "tab_uncited", count=len(uncited_df)),
                t(lang, "tab_matched", count=len(matched_df)),
            ])

            grid_height = 400
            select_mode = "single-row"
            
            def show_table(df, key_suffix):
                event = st.dataframe(
                    df, 
                    use_container_width=True, 
                    height=grid_height,
                    on_select="rerun", 
                    selection_mode=select_mode,
                    hide_index=True,
                    key=f"df_{key_suffix}"
                )
                return event

            with tab1:
                st.caption(t(lang, "missing_caption"))
                if not missing_df.empty:
                    evt = show_table(display_missing_df, "missing")
                    if evt.selection.rows:
                        row = missing_df.iloc[evt.selection.rows[0]]
                        if file_type == "pdf":
                            page_num = row.get("page", 1)
                            preview_caption = t(lang, "missing_preview_caption", page=page_num)
                            preview_img = get_pdf_page_image(file_bytes, page_num, row.get("citation_raw", ""))
                            waiting_for_selection = False
                else:
                    st.success(t(lang, "missing_empty_success"))

            with tab2:
                st.caption(t(lang, "uncited_caption"))
                if not uncited_df.empty:
                    evt = show_table(display_uncited_df, "uncited")
                    if evt.selection.rows:
                        row = uncited_df.iloc[evt.selection.rows[0]]
                        if file_type == "pdf":
                            page_num = row.get("page", 1)
                            preview_caption = t(lang, "uncited_preview_caption", page=page_num)
                            preview_img = get_pdf_page_image(file_bytes, page_num, row.get("參考文獻原文", ""))
                            waiting_for_selection = False
                else:
                    st.success(t(lang, "uncited_empty_success"))

            with tab3:
                st.caption(t(lang, "matched_caption"))
                if not matched_df.empty:
                    evt = show_table(display_matched_df, "matched")
                    if evt.selection.rows:
                        row = matched_df.iloc[evt.selection.rows[0]]
                        view_mode = st.radio(
                            t(lang, "preview_mode_label"),
                            options=["citation", "reference"],
                            format_func=lambda value: t(lang, f"preview_mode_{value}"),
                            horizontal=True,
                            label_visibility="collapsed",
                            key="preview_mode_selection",
                        )
                        
                        if file_type == "pdf":
                            if view_mode == "citation":
                                page_num = row.get("page", 1)
                                hl = row.get("citation_raw", "")
                                preview_caption = t(lang, "preview_body_caption", page=page_num)
                            else:
                                page_num = row.get("ref_page", 1)
                                hl = row.get("ref_raw", "")
                                preview_caption = t(lang, "preview_reference_caption", page=page_num)
                            preview_img = get_pdf_page_image(file_bytes, page_num, hl)
                            waiting_for_selection = False
                else:
                    st.info(t(lang, "matched_empty_info"))

        with col_right:
            if fitz is not None:
                if file_type == "docx":
                    st.warning(t(lang, "docx_preview_warning"))
                    st.info(t(lang, "docx_preview_tradeoff"))
                else:
                    st.info(preview_caption)
                    if preview_img:
                        st.image(preview_img, use_container_width=True)
                    elif file_type == "pdf" and waiting_for_selection:
                        st.write(t(lang, "preview_waiting"))
                    else:
                        st.write(t(lang, "preview_placeholder"))

        st.markdown("---")

        st.download_button(
            t(lang, "download_excel"),
            build_excel_report_bytes(summary_df, matched_df, missing_df, uncited_df, language=lang),
            t(lang, "excel_filename"),
            type="primary"
        )
