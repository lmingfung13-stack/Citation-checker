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
import pandas as pd
import streamlit as st
from PIL import Image
from services.convert_service import DOCX2PDF_AVAILABLE
from services.preview_service import get_pdf_page_image
from services.reference_service import (
    safe_normalize_reference_text,
    split_reference_items,
    match_citations,
)
from services.analysis_service import run_file_analysis
from services.export_service import build_excel_report_bytes
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

# Try to import PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF, need `pip install pymupdf`
except ImportError:
    fitz = None

st.set_page_config(page_title="論文文獻核對工具", layout="wide")

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

    /* === 修正：結束按鈕縮小、加上左側文字，並固定在右下角 === */
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
st.title("論文文獻核對工具")
st.warning("⚠️ **免責聲明**：本工具僅供輔助參考，無法取代人工校對。解析結果可能因檔案排版、OCR 品質或格式差異而有誤差，請務必自行確認原始文件。")

if fitz is None:
    st.error("錯誤：缺少 PDF 處理元件 (PyMuPDF)，預覽功能將無法使用。")

if "file_bytes" not in st.session_state:
    st.session_state.file_bytes = None
if "file_type" not in st.session_state:
    st.session_state.file_type = None
if "check_results" not in st.session_state:
    st.session_state.check_results = None
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

with st.expander("工具1：文獻列表整理（SAFE only）", expanded=False):
    raw_ref_text = st.text_area(
        "貼上原始文獻列表（raw）",
        key="ref_tool_raw_text",
        height=180,
    )
    if st.button("執行 SAFE 整理", key="ref_tool_run"):
        clean_text = safe_normalize_reference_text(raw_ref_text)
        st.session_state.ref_tool_raw_output = raw_ref_text
        st.session_state.ref_tool_clean_text = clean_text
        st.session_state.ref_tool_formatted_text = clean_text

        raw_items = split_reference_items(raw_ref_text)
        clean_items = split_reference_items(clean_text)
        sorted_clean_items = sorted(clean_items, key=lambda item: item.lower())
        st.session_state.ref_tool_sorted_output = "\n\n".join(sorted_clean_items) if sorted_clean_items else clean_text
        st.session_state.ref_tool_report = {
            "raw_items": len(raw_items),
            "clean_items": len(clean_items),
        }

    if st.session_state.ref_tool_clean_text is not None:
        report = st.session_state.ref_tool_report or {}
        st.caption(
            f"SAFE normalize 完成：raw_items={report.get('raw_items', 0)}, "
            f"clean_items={report.get('clean_items', 0)}（只做字元/空白正規化，不做推測合併拆分）"
        )
        st.text_area(
            "raw_text",
            value=st.session_state.ref_tool_raw_output or "",
            height=140,
        )
        st.text_area(
            "clean_text（工具2將優先使用）",
            value=st.session_state.ref_tool_clean_text or "",
            height=220,
        )
        st.text_area(
            "A-Z 排序顯示/輸出（僅改順序，不改內容）",
            value=st.session_state.ref_tool_sorted_output or "",
            height=220,
        )
        if st.session_state.ref_tool_sorted_output:
            st.download_button(
                "下載 clean list (.txt)",
                data=st.session_state.ref_tool_sorted_output,
                file_name="references_safe_clean_sorted.txt",
                mime="text/plain",
                key="ref_tool_download_txt",
            )

uploaded = st.file_uploader("請拖曳檔案至此 (支援 PDF / Word)", type=["docx", "pdf"])

if not uploaded:
    st.info("""
    💡 **操作步驟：**
    1. 將 Word 或 PDF 檔拖曳到上方框框。
    2. 等待程式自動分析。
    3. 點擊下方表格查看詳細結果。
    """)

if uploaded:
    raw_bytes = uploaded.getvalue()
    raw_type = uploaded.name.split(".")[-1].lower()
    
    use_conversion = False
    
    status_container = st.container()
    metrics_container = st.container()
    st.markdown("---")
    col_left, col_right = st.columns([1.5, 1])

    with col_right:
        st.subheader("📄 預覽視窗")
        if fitz is None:
            st.error("預覽功能失效 (缺 PyMuPDF)")
        elif raw_type == "docx":
            if DOCX2PDF_AVAILABLE:
                st.info("💡 目前為純文字核對模式。")
                use_conversion = st.checkbox("啟用 Word 轉 PDF 視覺化預覽 (需稍候幾秒)", value=False)
                st.markdown("---")
            else:
                st.caption("目前僅支援 Word 純文字核對 (未偵測到轉檔元件)。")
                st.markdown("---")

    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    current_key = f"{uploaded.name}_{use_conversion}_{content_hash}"

    with status_container:
        conversion_pending = False

        if st.session_state.last_processed_key != current_key:
            st.session_state.filename = uploaded.name
            st.session_state.check_results = None
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
                st.warning("Conversion job expired. Please resubmit.")
                if st.button("Resubmit conversion", key=f"retry_docx_pdf_{content_hash}"):
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
                    st.success("Conversion succeeded. Preview mode enabled.")
                st.session_state.file_bytes = job.result_bytes
                st.session_state.file_type = "pdf"
            elif job.status == JOB_STATUS_FAILED:
                st.session_state.file_bytes = raw_bytes
                st.session_state.file_type = "docx"
                st.error("Conversion timed out or failed (Word not responding). Switched back to text mode.")
            elif job.status == JOB_STATUS_CANCELED:
                st.session_state.file_bytes = raw_bytes
                st.session_state.file_type = "docx"
                st.warning("Conversion canceled.")
                if st.button("Resubmit conversion", key=f"retry_canceled_docx_pdf_{content_hash}"):
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
                st.info("Word conversion queued...")
                if st.button("Cancel conversion", key=f"cancel_docx_pdf_{active_job_id}"):
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
                st.info("Word conversion running...")
                if st.button("Cancel conversion", key=f"cancel_docx_pdf_{active_job_id}"):
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
                with st.spinner("Analyzing citations..."):
                    results = run_file_analysis(
                        file_bytes=file_bytes,
                        filename=st.session_state.filename,
                        file_type=file_type,
                    )
                    st.session_state.check_results = results
            except ReferenceSectionNotFoundError as e:
                st.error(f"{e.message}")
                st.stop()
            except AppError as e:
                st.error(f"{e.message}")
                st.stop()
            except Exception as e:
                st.error(f"Analysis error: {e}")
                st.stop()

    summary_df, matched_df, missing_df, uncited_df = st.session_state.check_results

    safe_linked_match_result = None
    safe_clean_text = st.session_state.get("ref_tool_clean_text") or ""
    if safe_clean_text.strip():
        citation_raw_parts = []
        for frame in (matched_df, missing_df):
            if isinstance(frame, pd.DataFrame) and "citation_raw" in frame.columns:
                for value in frame["citation_raw"].tolist():
                    value_text = str(value).strip()
                    if value_text:
                        citation_raw_parts.append(value_text)

        if citation_raw_parts:
            try:
                clean_reference_items = split_reference_items(safe_clean_text)
                safe_linked_match_result = match_citations(
                    text="\n".join(citation_raw_parts),
                    reference_items=clean_reference_items,
                )
            except Exception:
                safe_linked_match_result = None

    with metrics_container:
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("成功配對", len(matched_df))
        col_m2.metric("遺漏引用 (需補)", len(missing_df), delta_color="inverse")
        col_m3.metric("未被引用 (需刪)", len(uncited_df), delta_color="inverse")
        if safe_linked_match_result is not None:
            st.caption("已使用工具1的 clean_text（SAFE normalize）做 citation key 比對。")
            st.caption(
                f"key matched={len(safe_linked_match_result.get('matched', []))}, "
                f"missing_in_reference={len(safe_linked_match_result.get('missing_in_reference', []))}, "
                f"extra_in_reference={len(safe_linked_match_result.get('extra_in_reference', []))}"
            )
            with st.expander("SAFE key 比對明細", expanded=False):
                st.write("matched:", safe_linked_match_result.get("matched", []))
                st.write("missing_in_reference:", safe_linked_match_result.get("missing_in_reference", []))
                st.write("extra_in_reference:", safe_linked_match_result.get("extra_in_reference", []))

    preview_img = None
    preview_caption = "👈 點擊左側表格行可預覽內容"

    with col_left:
        tab1, tab2, tab3 = st.tabs([
            f"❌ 遺漏引用 ({len(missing_df)})",
            f"⚠️ 未被引用 ({len(uncited_df)})",
            f"✅ 成功配對 ({len(matched_df)})",
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
            st.caption("正文有引用，但參考文獻列表找不到。")
            if not missing_df.empty:
                evt = show_table(missing_df, "missing")
                if evt.selection.rows:
                    row = missing_df.iloc[evt.selection.rows[0]]
                    if file_type == "pdf":
                        page_num = row.get("page", 1)
                        preview_caption = f"遺漏引用 - Page {page_num}"
                        preview_img = get_pdf_page_image(file_bytes, page_num, row.get("citation_raw", ""))
            else:
                st.success("太棒了！沒有發現遺漏的引用。")

        with tab2:
            st.caption("出現在文獻列表，但正文未引用。")
            if not uncited_df.empty:
                evt = show_table(uncited_df, "uncited")
                if evt.selection.rows:
                    row = uncited_df.iloc[evt.selection.rows[0]]
                    if file_type == "pdf":
                        page_num = row.get("page", 1)
                        preview_caption = f"未被引用 - Page {page_num}"
                        preview_img = get_pdf_page_image(file_bytes, page_num, row.get("參考文獻原文", ""))
            else:
                st.success("完美！所有參考文獻都有被使用。")

        with tab3:
            st.caption("配對成功的項目。")
            if not matched_df.empty:
                evt = show_table(matched_df, "matched")
                if evt.selection.rows:
                    row = matched_df.iloc[evt.selection.rows[0]]
                    view_mode = st.radio("預覽位置", ["正文引用", "參考文獻"], horizontal=True, label_visibility="collapsed")
                    
                    if file_type == "pdf":
                        if view_mode == "正文引用":
                            page_num = row.get("page", 1)
                            hl = row.get("citation_raw", "")
                            preview_caption = f"正文 - Page {page_num}"
                        else:
                            page_num = row.get("ref_page", 1)
                            hl = row.get("ref_raw", "")
                            preview_caption = f"文獻列表 - Page {page_num}"
                        preview_img = get_pdf_page_image(file_bytes, page_num, hl)
            else:
                st.info("尚未有配對結果。")

    with col_right:
        if fitz is not None:
            if file_type == "docx":
                st.warning("⚠️ Word 純文字模式不支援圖片預覽。請勾選上方選項啟用。")
                st.info("""
                💡 **關於轉檔模式的取捨：**
                * **優點 (Pros)**：可啟用視覺化預覽，程式會用紅框自動標示出引用的位置，人工核對更直覺。
                * **缺點 (Cons)**：需等待轉檔時間，且 PDF 的解析精準度通常略低於 Word 純文字模式（文字可能因排版而破碎或誤判）。
                """)
            else:
                st.info(preview_caption)
                if preview_img:
                    st.image(preview_img, use_container_width=True)
                elif file_type == "pdf" and "點擊" in preview_caption:
                    st.write("等待選取...")
                else:
                    st.write("...")

    st.markdown("---")

    st.download_button(
        "📥 下載 Excel 完整報告",
        build_excel_report_bytes(summary_df, matched_df, missing_df, uncited_df),
        "citation_report.xlsx",
        type="primary"
    )
