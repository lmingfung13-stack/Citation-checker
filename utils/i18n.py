from __future__ import annotations

from typing import Any

import pandas as pd

LANG_ZH = "zh"
LANG_EN = "en"
SUPPORTED_LANGS = (LANG_ZH, LANG_EN)

_TEXTS: dict[str, dict[str, str]] = {
    LANG_ZH: {
        "page_title": "論文文獻核對工具",
        "app_title": "論文文獻核對工具",
        "language_label": "Language / 語言",
        "language_option_zh": "中文",
        "language_option_en": "English",
        "disclaimer": "⚠️ **免責聲明**：本工具僅供輔助參考，無法取代人工校對。解析結果可能因檔案排版、OCR 品質或格式差異而有誤差，請務必自行確認原始文件。",
        "error_missing_pymupdf": "錯誤：缺少 PDF 處理元件 (PyMuPDF)，預覽功能將無法使用。",
        "tab_tool1": "文獻列表排列",
        "tab_tool2": "文獻對比",
        "tool1_input_label": "貼上文獻列表",
        "tool1_run_button": "執行整理",
        "tool1_done_caption": "整理完成：原始筆數={raw_items}, 整理後筆數={clean_items}",
        "tool1_result_label": "結果",
        "tool1_download_txt": "下載結果(.txt)",
        "tool1_download_filename": "references_safe_clean_sorted.txt",
        "tool1_empty_info": "尚未產生整理結果。請貼上文獻列表後執行整理。",
        "uploader_label": "請拖曳檔案至此 (支援 PDF / Word)",
        "reference_source_label": "文獻來源",
        "reference_source_tool1": "使用工具1整理後文獻列表提高準確度",
        "reference_source_auto": "使用文件自動抽取的文獻列表",
        "auto_switch_info": "偵測到工具1尚無可用整理結果，已自動切換為「使用文件自動抽取的文獻列表」。",
        "steps_info": "💡 **操作步驟：**\n1. 將 Word 或 PDF 檔拖曳到上方框框。\n2. 等待程式自動分析。\n3. 點擊下方表格查看詳細結果。",
        "preview_title": "📄 預覽視窗",
        "preview_disabled_missing_pymupdf": "預覽功能失效 (缺 PyMuPDF)",
        "preview_text_mode_info": "💡 目前為純文字核對模式。",
        "preview_enable_docx_pdf": "啟用 Word 轉 PDF 視覺化預覽 (需稍候幾秒)",
        "preview_docx_no_converter": "目前僅支援 Word 純文字核對 (未偵測到轉檔元件)。",
        "override_fallback_info": "目前尚無工具1整理結果，本次將改用文件自動抽取的文獻列表。",
        "conversion_job_expired": "轉檔工作已過期，請重新提交。",
        "conversion_resubmit": "重新提交轉檔",
        "conversion_success": "轉檔成功，已啟用預覽模式。",
        "conversion_failed": "轉檔逾時或失敗（Word 無回應），已切回純文字模式。",
        "conversion_canceled": "已取消轉檔。",
        "conversion_queued": "Word 轉檔已排隊...",
        "conversion_running": "Word 轉檔進行中...",
        "conversion_cancel": "取消轉檔",
        "analyzing": "分析引用中...",
        "analysis_error": "分析失敗：{error}",
        "analysis_error_reference_section": "找不到參考文獻區段，請確認文件格式。",
        "analysis_error_app": "處理失敗：{error}",
        "error_detail_caption": "詳細資訊：{detail}",
        "metric_matched": "Matched",
        "metric_missing": "Missing In-Text",
        "metric_uncited": "Uncited References",
        "source_caption_tool1": "文獻來源：使用工具1整理後文獻列表（筆數={count}）",
        "source_caption_auto": "文獻來源：文件自動抽取文獻列表（筆數={count}）",
        "warning_with_detail": "警告：{detail}",
        "preview_default_hint": "👈 點擊左側表格行可預覽內容",
        "tab_missing": "❌ 遺漏引用 ({count})",
        "tab_uncited": "⚠️ 未被引用 ({count})",
        "tab_matched": "✅ 成功配對 ({count})",
        "missing_caption": "正文有引用，但參考文獻列表找不到。",
        "missing_preview_caption": "遺漏引用 - Page {page}",
        "missing_empty_success": "太棒了！沒有發現遺漏的引用。",
        "uncited_caption": "出現在文獻列表，但正文未引用。",
        "uncited_preview_caption": "未被引用 - Page {page}",
        "uncited_empty_success": "完美！所有參考文獻都有被使用。",
        "matched_caption": "配對成功的項目。",
        "matched_empty_info": "尚未有配對結果。",
        "preview_mode_label": "預覽位置",
        "preview_mode_citation": "正文引用",
        "preview_mode_reference": "參考文獻",
        "preview_body_caption": "正文 - Page {page}",
        "preview_reference_caption": "文獻列表 - Page {page}",
        "docx_preview_warning": "⚠️ Word 純文字模式不支援圖片預覽。請勾選上方選項啟用。",
        "docx_preview_tradeoff": "💡 **關於轉檔模式的取捨：**\n* **優點 (Pros)**：可啟用視覺化預覽，程式會用紅框自動標示出引用的位置，人工核對更直覺。\n* **缺點 (Cons)**：需等待轉檔時間，且 PDF 的解析精準度通常略低於 Word 純文字模式（文字可能因排版而破碎或誤判）。",
        "preview_waiting": "等待選取...",
        "preview_placeholder": "...",
        "download_excel": "📥 下載 Excel 完整報告",
        "excel_filename": "citation_report.xlsx",
    },
    LANG_EN: {
        "page_title": "Citation Checker",
        "app_title": "Citation Checker",
        "language_label": "Language / 語言",
        "language_option_zh": "中文",
        "language_option_en": "English",
        "disclaimer": "⚠️ **Disclaimer**: This tool assists citation checking only and does not replace manual review. Results may vary due to layout, OCR quality, or formatting differences. Please verify against the original document.",
        "error_missing_pymupdf": "Error: Missing PDF component (PyMuPDF). Preview is unavailable.",
        "tab_tool1": "Reference List Cleanup",
        "tab_tool2": "Citation Matching",
        "tool1_input_label": "Paste Reference List",
        "tool1_run_button": "Run Cleanup",
        "tool1_done_caption": "Cleanup completed: raw count={raw_items}, cleaned count={clean_items}",
        "tool1_result_label": "Result",
        "tool1_download_txt": "Download Result (.txt)",
        "tool1_download_filename": "references_safe_clean_sorted.txt",
        "tool1_empty_info": "No cleanup result yet. Paste a reference list and run cleanup.",
        "uploader_label": "Drag and drop file here (PDF / Word)",
        "reference_source_label": "Reference Source",
        "reference_source_tool1": "Use cleaned list from Tool 1 (higher accuracy)",
        "reference_source_auto": "Use auto-extracted references from document",
        "auto_switch_info": "No usable Tool 1 output detected. Switched to auto-extracted references.",
        "steps_info": "💡 **How to use:**\n1. Drag a Word or PDF file into the uploader.\n2. Wait for automatic analysis.\n3. Click rows in the tables below to inspect details.",
        "preview_title": "📄 Preview",
        "preview_disabled_missing_pymupdf": "Preview unavailable (missing PyMuPDF).",
        "preview_text_mode_info": "💡 Text-only checking mode is active.",
        "preview_enable_docx_pdf": "Enable Word-to-PDF visual preview (may take a few seconds)",
        "preview_docx_no_converter": "Word text-only mode only (conversion component not detected).",
        "override_fallback_info": "No Tool 1 output available. Using auto-extracted references for this run.",
        "conversion_job_expired": "Conversion job expired. Please resubmit.",
        "conversion_resubmit": "Resubmit conversion",
        "conversion_success": "Conversion succeeded. Preview mode enabled.",
        "conversion_failed": "Conversion timed out or failed (Word not responding). Switched back to text mode.",
        "conversion_canceled": "Conversion canceled.",
        "conversion_queued": "Word conversion queued...",
        "conversion_running": "Word conversion running...",
        "conversion_cancel": "Cancel conversion",
        "analyzing": "Analyzing citations...",
        "analysis_error": "Analysis error: {error}",
        "analysis_error_reference_section": "Reference section not found. Please verify the document format.",
        "analysis_error_app": "Processing failed: {error}",
        "error_detail_caption": "Details: {detail}",
        "metric_matched": "Matched",
        "metric_missing": "Missing In-Text",
        "metric_uncited": "Uncited References",
        "source_caption_tool1": "Reference source: Tool 1 cleaned list (count={count})",
        "source_caption_auto": "Reference source: auto-extracted from document (count={count})",
        "warning_with_detail": "Warning: {detail}",
        "preview_default_hint": "👈 Click a row on the left to preview",
        "tab_missing": "❌ Missing In-Text ({count})",
        "tab_uncited": "⚠️ Uncited References ({count})",
        "tab_matched": "✅ Matched ({count})",
        "missing_caption": "Cited in body but not found in the reference list.",
        "missing_preview_caption": "Missing In-Text - Page {page}",
        "missing_empty_success": "Great! No missing in-text citations found.",
        "uncited_caption": "Present in reference list but not cited in the body.",
        "uncited_preview_caption": "Uncited Reference - Page {page}",
        "uncited_empty_success": "Great! All references are cited.",
        "matched_caption": "Successfully matched items.",
        "matched_empty_info": "No matched items yet.",
        "preview_mode_label": "Preview Target",
        "preview_mode_citation": "In-Text Citation",
        "preview_mode_reference": "Reference Entry",
        "preview_body_caption": "Body - Page {page}",
        "preview_reference_caption": "Reference List - Page {page}",
        "docx_preview_warning": "⚠️ Image preview is unavailable in Word text-only mode. Enable conversion above.",
        "docx_preview_tradeoff": "💡 **Conversion mode trade-offs:**\n* **Pros**: Enables visual preview and highlights citation areas for faster manual checks.\n* **Cons**: Requires conversion time, and PDF parsing is usually less accurate than Word text-only parsing.",
        "preview_waiting": "Waiting for selection...",
        "preview_placeholder": "...",
        "download_excel": "📥 Download Full Excel Report",
        "excel_filename": "citation_report.xlsx",
    },
}

_COLUMN_MAPS: dict[str, dict[str, str]] = {
    "summary": {
        "正文段落數": "Body Paragraphs",
        "參考文獻項目數": "Reference Items",
        "正文引用數": "In-Text Citations",
        "成功配對數": "Matched",
        "缺失引用數（正文有/文末無）": "Missing In-Text (in body, not in references)",
        "未引用文獻數（文末有/正文無）": "Uncited References (in references, not in body)",
    },
    "matched": {
        "citation_raw": "Citation Raw",
        "lang": "Language",
        "author1": "Author 1",
        "year": "Year",
        "para_idx": "Paragraph Index",
        "context": "Context",
        "page": "Body Page",
        "match_type": "Match Type",
        "ref_raw": "Reference Raw",
        "ref_page": "Reference Page",
    },
    "missing": {
        "citation_raw": "Citation Raw",
        "lang": "Language",
        "author1": "Author 1",
        "year": "Year",
        "para_idx": "Paragraph Index",
        "context": "Context",
        "page": "Body Page",
    },
    "uncited": {
        "文獻索引": "Reference Index",
        "語言": "Language",
        "第一作者": "First Author",
        "年份": "Year",
        "參考文獻原文": "Reference Raw",
        "page": "Reference Page",
    },
}

_SHEET_NAMES: dict[str, dict[str, str]] = {
    LANG_ZH: {
        "summary": "摘要",
        "matched": "成功配對",
        "missing": "缺失引用",
        "uncited": "未被引用",
    },
    LANG_EN: {
        "summary": "Summary",
        "matched": "Matched",
        "missing": "Missing In-Text",
        "uncited": "Uncited References",
    },
}


def normalize_lang(lang: str | None) -> str:
    if lang in SUPPORTED_LANGS:
        return str(lang)
    return LANG_ZH


def t(lang: str | None, key: str, **kwargs: Any) -> str:
    language = normalize_lang(lang)
    table = _TEXTS.get(language, _TEXTS[LANG_ZH])
    template = table.get(key) or _TEXTS[LANG_ZH].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template


def localize_df_columns(df: pd.DataFrame, table_kind: str, lang: str | None) -> pd.DataFrame:
    if normalize_lang(lang) == LANG_ZH:
        return df.copy()
    col_map = _COLUMN_MAPS.get(table_kind, {})
    return df.rename(columns=col_map).copy()


def sheet_name_for(table_kind: str, lang: str | None) -> str:
    language = normalize_lang(lang)
    return _SHEET_NAMES.get(language, _SHEET_NAMES[LANG_ZH]).get(table_kind, table_kind)
