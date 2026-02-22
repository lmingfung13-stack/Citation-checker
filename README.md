🔗 Live Demo/線上使用: https://citation-checker-emkbmr3cbkwmgidhpycysx.streamlit.app/

# Citation Checker [下有中文說明]

Academic Citation & Reference Validation Tool

Citation Checker is a Streamlit-based application designed to validate in-text citations against reference lists. It helps authors identify missing references, uncited entries, and inconsistencies before manuscript submission.

---

## Core Features

### Tool 1: Reference List Normalization (Reference Cleaner)

This module processes pasted reference text using a SAFE normalization approach:

* Cleans irregular line breaks and formatting noise
* Standardizes structural layout
* Outputs a normalized `clean_text` version

The cleaned output can be:

* Copied directly back into Word
* Downloaded as a `.txt` file

This normalized reference list can also be used as an input source for Tool 2 to improve matching consistency.

---

### Tool 2: Citation–Reference Matching

Supports uploading PDF or Word documents. The system automatically extracts:

* In-text citations
* Reference list entries

It then compares both sources and categorizes results into three groups:

* **Matched** – In-text citations successfully paired with reference entries
* **Missing** – Citations appearing in the text but absent from the reference list
* **Uncited** – Reference entries that are not cited in the main text

If Tool 1 has been used, users may choose to override the automatically extracted reference list with the normalized `clean_text` to ensure structural consistency during matching.

---

## Exported Output

Results can be downloaded as `citation_report.xlsx`, which includes four worksheets:

1. **Summary** – Overall matching statistics
2. **Matched** – Successfully paired citations
3. **Missing** – Unlisted citations detected in text
4. **Uncited** – References not cited in the document

---

## Use Cases

* Pre-submission manuscript validation
* Thesis citation integrity checks
* Research assistant document auditing
* Instructor-level citation completeness review

-----------------------------------------------------------------------------------------------------------------

# Citation Checker

Academic Citation & Reference Validation Tool

Citation Checker 是一個以 Streamlit 建構的學術引用檢查工具，用於比對「正文 citation」與「參考文獻列表」，協助使用者在投稿或論文提交前發現遺漏與錯置問題。

---

## 核心功能

### 工具1：文獻列表正規化（Reference Cleaner）

將使用者貼上的 references 文字進行 SAFE 正規化處理：

* 清理異常換行與格式雜訊
* 統一文字結構
* 產出 `clean_text`

整理後的文字可：

* 直接複製回 Word
* 或下載為 `.txt` 檔案保存

此功能可作為工具2的前處理來源。

---

### 工具2：Citation / Reference 比對分析

支援上傳 PDF 或 Word 檔案，自動抽取：

* 正文中的 citation
* 文末 reference 區段

系統會將兩者進行比對，並分類為三種結果：

* matched：正文引用與文獻列表成功配對
* missing：正文出現 citation，但文獻列表未列出
* uncited：文獻列表存在條目，但正文未引用

若已先使用工具1整理 references，可選擇以 `clean_text` 覆蓋自動抽取的 reference 來源，提高比對一致性。

---

## 分析輸出

分析結果可匯出為 `citation_report.xlsx`，包含四個工作表：

1. Summary：整體統計摘要
2. Matched：成功配對清單
3. Missing：缺失引用清單
4. Uncited：未被引用文獻清單

---

## 適用情境

* 論文投稿前引用檢查
* 研究助理協助大量文稿檢核
* 指導教授快速檢視學生引用完整性

---
