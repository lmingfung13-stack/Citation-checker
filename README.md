# 引用與文獻比對工具

本專案提供兩個主要功能：

1. 文獻列表整理（工具1）
- 對使用者貼上的 references 文字做 SAFE 正規化。
- 產出 `clean_text`，可直接複製到 Word 或下載 `.txt`。

2. 內文 citation 與 reference 比對（工具2）
- 讀取 PDF / Word，抽取正文 citation 與文末 reference。
- 輸出 `matched / missing / uncited` 三類結果。
- 若已先使用工具1，可選擇用整理後 `clean_text` 覆蓋自動抽取的 reference 來源。

## 執行方式

```bash
streamlit run app.py
```

## 匯出

分析結果可下載為 `citation_report.xlsx`，包含摘要、成功配對、缺失引用、未被引用四個工作表。
