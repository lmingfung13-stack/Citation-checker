# -*- coding: utf-8 -*-

import re
import io
import difflib
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Set
import pandas as pd
from docx import Document

# Try to import pdfplumber, handle case if not installed
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# -------------------------
# Config
# -------------------------

REFERENCE_HEADINGS = ["參考文獻", "參考資料", "references", "reference", "bibliography"]
REFERENCE_TAIL_STOP_HEADINGS = [
    "技術手冊、準則與報告",
    "technical manuals, standards and reports",
    "technical manuals, standards & reports",
]

FULLWIDTH_TO_HALFWIDTH = {
    "（": "(", "）": ")", "＆": "&", "’": "'", "‘": "'",
    "‐": "-", "‑": "-", "–": "-", "—": "-",
    "，": ",", "‚": ",", "¸": ",", "､": ",", "。": ".",
}

CITATION_LIST_SEP_PATTERN = r"[;；]"
CITATION_SECONDARY_SEP_PATTERN = r"[、,，]"
YEAR_PATTERN_STR = r"(?:[12]\d{3}|n\.?d\.?|no\s*date|in\s*press|印刷中|未刊)"
ENG_CHARS = r"A-Za-z\u00C0-\u00FF"

# -------------------------
# Data structures
# -------------------------

@dataclass
class DocParagraph:
    """用來儲存段落文字及其對應的頁碼"""
    text: str
    page: int  # 1-based page number

@dataclass
class InTextCitation:
    lang: str
    author1: str
    author2: Optional[str]
    year: str
    raw: str
    para_idx: int
    context: str
    page: int  # 新增：所在頁碼

@dataclass
class ReferenceItem:
    lang: str
    author1: str
    author2: Optional[str]
    year: str
    raw: str
    item_idx: int
    page: int  # 新增：所在頁碼

# -------------------------
# Normalization helpers
# -------------------------

def normalize_text(s: str) -> str:
    if not s: return s
    s = re.sub(r"[\u200b\u200e\u200f\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    for k, v in FULLWIDTH_TO_HALFWIDTH.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def remove_accents(input_str: str) -> str:
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def is_english_author_token(s: str) -> bool:
    return bool(re.search(f"[{ENG_CHARS}]", s))

def norm_english_surname(s: str) -> str:
    if "," in s: s = s.split(",")[0]
    s = re.sub(r"\s+[" + ENG_CHARS + r"]\.", "", s)
    s = re.sub(r"\s+[" + ENG_CHARS + r"]$", "", s)
    s = re.sub(r"([a-z])[A-Z]{1,3}$", r"\1", s)
    s = remove_accents(s)
    s = s.lower().replace(".", "").strip()
    return re.sub(r"\s+", " ", s)

def norm_chinese_name(s: str) -> str:
    return re.sub(r"\s+", "", s.strip())

def norm_year(y: str) -> str:
    y = y.strip().lower()
    if "n.d" in y or "no date" in y: base = "n.d."
    elif "press" in y or "印刷" in y or "未刊" in y: base = "in press"
    else:
        m = re.search(r"([12]\d{3})", y)
        base = m.group(1) if m else y

    suffix = ""
    if re.search(r"\d$", base): 
        m_suffix = re.search(r"([a-z])$", y)
        if m_suffix: suffix = m_suffix.group(1)
    else:
        m_suffix = re.search(r"[- ]([a-z])$", y)
        if m_suffix: suffix = m_suffix.group(1)
            
    return base + suffix

def citation_key(c: InTextCitation) -> Tuple[str, str, Optional[str], str]:
    a1 = norm_english_surname(c.author1) if c.lang == "en" else norm_chinese_name(c.author1)
    a2 = None
    if c.author2:
        a2 = norm_english_surname(c.author2) if c.lang == "en" else norm_chinese_name(c.author2)
    return (c.lang, a1, a2, norm_year(c.year))

def reference_key(r: ReferenceItem) -> Tuple[str, str, Optional[str], str]:
    a1 = norm_english_surname(r.author1) if r.lang == "en" else norm_chinese_name(r.author1)
    a2 = None
    if r.author2:
        a2 = norm_english_surname(r.author2) if r.lang == "en" else norm_chinese_name(r.author2)
    return (r.lang, a1, a2, norm_year(r.year))

def is_similar_str(s1: str, s2: str, threshold: float = 0.75) -> bool:
    if not s1 or not s2: return False
    if len(s1) <= 4 or len(s2) <= 4: return s1.lower() == s2.lower()
    s1 = remove_accents(s1).lower()
    s2 = remove_accents(s2).lower()
    return difflib.SequenceMatcher(None, s1, s2).ratio() >= threshold

# -------------------------
# File reading (Word & PDF)
# -------------------------

def read_docx_bytes(b: bytes) -> List[DocParagraph]:
    doc = Document(io.BytesIO(b))
    # Word doc 沒有明確的「頁碼」概念，預設為 1 (若是未轉檔的 fallback 狀況)
    return [DocParagraph(p.text, 1) for p in doc.paragraphs]

def extract_text_smart_layout(page) -> str:
    width = page.width
    height = page.height
    words = page.extract_words()
    
    if not words: return ""

    gutter_x0 = width * 0.40
    gutter_x1 = width * 0.60
    
    gutter_words = [w for w in words if not (w['x1'] < gutter_x0 or w['x0'] > gutter_x1)]
    
    is_two_col = False
    y_split = 0
    
    if not gutter_words:
        is_two_col = True
    else:
        gutter_words.sort(key=lambda w: w['bottom'])
        lowest_gutter_word = gutter_words[-1]
        if lowest_gutter_word['bottom'] < height * 0.20:
            is_two_col = True
            y_split = lowest_gutter_word['bottom'] + 5 
    
    text_parts = []
    if is_two_col:
        if y_split > 0:
            header_box = (0, 0, width, y_split)
            header_text = page.within_bbox(header_box).extract_text()
            if header_text: text_parts.append(header_text)
        
        left_box = (0, y_split, width * 0.5, height)
        if left_box[3] > left_box[1]:
            try:
                left_text = page.within_bbox(left_box).extract_text()
                if left_text: text_parts.append(left_text)
            except ValueError: pass

        right_box = (width * 0.5, y_split, width, height)
        if right_box[3] > right_box[1]:
            try:
                right_text = page.within_bbox(right_box).extract_text()
                if right_text: text_parts.append(right_text)
            except ValueError: pass
        return "\n".join(text_parts)
    else:
        return page.extract_text() or ""

def read_pdf_bytes(b: bytes) -> List[DocParagraph]:
    if pdfplumber is None:
        raise ImportError("請先安裝 pdfplumber 套件: pip install pdfplumber")
    
    paragraphs = []
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for page in pdf.pages:
            text = extract_text_smart_layout(page)
            if text:
                lines = text.split('\n')
                for line in lines:
                    # 關鍵：將每一行都標記為當前頁碼
                    paragraphs.append(DocParagraph(line, page.page_number))
    return paragraphs

# -------------------------
# Helper: Find Reference Section
# -------------------------

def find_reference_section_start(paragraphs: List[DocParagraph]) -> Optional[int]:
    for i, p in enumerate(paragraphs):
        t = normalize_text(p.text).strip().lower()
        if t in [h.lower() for h in REFERENCE_HEADINGS]: return i
    for i, p in enumerate(paragraphs):
        t = normalize_text(p.text).strip().lower()
        t_nospace = t.replace(" ", "")
        if t_nospace in [h.lower() for h in REFERENCE_HEADINGS]: return i
    for i, p in enumerate(paragraphs):
        t = normalize_text(p.text).strip().lower()
        if len(t) <= 40: 
            if any(h.lower() in t for h in REFERENCE_HEADINGS): return i
    return None


def _looks_like_reference_tail_heading(text: str) -> bool:
    t = normalize_text(text).strip()
    if not t:
        return False
    if len(t) > 60:
        return False
    if re.search(r"(?:19|20)\d{2}", t):
        return False
    compact = re.sub(r"[\W_]+", "", t.lower())
    for marker in REFERENCE_TAIL_STOP_HEADINGS:
        marker_compact = re.sub(r"[\W_]+", "", marker.lower())
        if marker_compact and marker_compact in compact:
            return True
    return False


def _looks_like_non_reference_tail_content(text: str) -> bool:
    t = normalize_text(text).strip()
    if not t:
        return False
    # Stop before table/appendix content that often appears after reference lists.
    if re.match(r"^(?:表\s*[一二三四五六七八九十\d]+|table\s*[ivx\d]+)\b", t, re.IGNORECASE):
        return True
    if re.match(r"^(?:附錄|appendix)\b", t, re.IGNORECASE):
        return True
    if "產業樣本年度分析" in t or "年度產業類別" in t:
        return True
    return False


def _looks_like_running_header_footer_noise(text: str) -> bool:
    t = normalize_text(text).strip()
    if not t:
        return False
    if re.fullmatch(r"\d{1,4}", t):
        return True
    low = t.lower()
    if "this content downloaded from" in low or "all use subject to" in low:
        return True
    if re.match(r"^\d+\s+[A-Za-z][A-Za-z\-\s\.]{8,}$", t) and not any(ch in t for ch in ",()"):
        return True
    if (
        re.match(r"^(?:[A-Z][A-Za-z'\-]+\s+){2,}[A-Z][A-Za-z'\-]+$", t)
        and not any(ch in t for ch in ",()")
        and not re.search(r"(?:19|20)\d{2}", t)
    ):
        return True
    return False

# -------------------------
# Reference parsing
# -------------------------

def extract_reference_items(paragraphs: List[DocParagraph], start_idx: int) -> List[ReferenceItem]:
    raw_paras: List[DocParagraph] = []
    for p in paragraphs[start_idx + 1:]:
        t = normalize_text(p.text)
        if not t:
            continue
        if _looks_like_running_header_footer_noise(t):
            continue
        # Stop when encountering known non-reference appendix headings.
        if _looks_like_reference_tail_heading(t) or _looks_like_non_reference_tail_content(t):
            break
        raw_paras.append(p)
    if not raw_paras: return []

    year_re = re.compile(r"\(" + YEAR_PATTERN_STR + r"([- ]?[a-zA-Z])?\)")
    year_any_parenthetical_re = re.compile(r"\([^\)]*(?:19|20)\d{2}[^\)]*\)")
    chinese_year_re = re.compile(r"(?:[,，\s]|^)\s*(" + YEAR_PATTERN_STR + r")\s*[,，\.]")
    english_dot_year_re = re.compile(r"(?:[\.\s])(" + YEAR_PATTERN_STR + r")\.")

    def looks_like_new_item(t: str) -> bool:
        t = t.strip()
        if year_re.search(t) and re.match(r"^[A-Za-z\u4e00-\u9fff]", t): return True
        if year_any_parenthetical_re.search(t) and re.match(r"^[A-Za-z]", t): return True
        if re.match(r"^[" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s]+,\s+[" + ENG_CHARS + r"]\.", t): return True
        if re.search(r"^[A-Z][a-z]+[A-Z]{1,3}\(" + YEAR_PATTERN_STR + r"\)", t): return True
        if re.match(r"^[\u4e00-\u9fff]", t) and chinese_year_re.search(t): return True
        if re.match(r"^[A-Z]", t) and english_dot_year_re.search(t): return True
        return False

    def should_force_append(current_text: str, next_text: str) -> bool:
        curr = normalize_text(current_text).strip()
        nxt = normalize_text(next_text).strip()
        if not curr or not nxt:
            return False
        if curr.endswith((".", "。", ".)", ".”", "\"")):
            return False
        if not year_re.search(curr):
            return False
        # If next line starts with a strong author-start pattern, keep split behavior.
        if re.match(r"^[" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s]+,\s+[" + ENG_CHARS + r"]\.", nxt):
            return False
        if re.match(r"^[\u4e00-\u9fff]", nxt) and chinese_year_re.search(nxt):
            return False
        # If next line has no year marker, treat as continuation of current reference.
        if not year_re.search(nxt) and not year_any_parenthetical_re.search(nxt):
            return True
        return False
    
    merged_paras: List[DocParagraph] = []
    i = 0
    zh_end_re = re.compile(r"[\u4e00-\u9fff]\s*$")
    ends_with_connector_re = re.compile(r"(?:,|and|&)\s*$", re.IGNORECASE)

    while i < len(raw_paras):
        curr_p = raw_paras[i]
        text_buf = curr_p.text
        # 合併段落時，頁碼以起始行為準
        page_buf = curr_p.page 
        
        while i + 1 < len(raw_paras):
            next_p = raw_paras[i+1]
            next_text = next_p.text
            should_merge = False
            
            if text_buf.endswith("-") or text_buf.endswith("–"):
                if next_text and next_text[0].isupper():
                     text_buf = text_buf + next_text.strip() 
                else:
                     text_buf = text_buf[:-1] + next_text.strip()
                should_merge = True
            elif zh_end_re.search(text_buf):
                text_buf = text_buf.strip() + next_text.strip()
                should_merge = True
            elif ends_with_connector_re.search(text_buf):
                text_buf = text_buf.strip() + " " + next_text.strip()
                should_merge = True

            if should_merge:
                i += 1
            else:
                break
        merged_paras.append(DocParagraph(text_buf, page_buf))
        i += 1
        
    split_page_range_re = re.compile(r"(\d{2,5}[-–]\d{2,5}[.．]?)")
    split_zh_smart_re = re.compile(r"([\u4e00-\u9fff]{2,3}(?:[、與和][\u4e00-\u9fff]+)*[,，\s]+(?:19|20)\d{2}[,，\.])")
    split_en_re = re.compile(r"(?<=\d\.)\s+(?=[A-Z][a-zA-Z' -]+,)")
    split_mashed_re = re.compile(r"\s+(?=[A-Z][a-z]+[A-Z]{1,3}\(" + YEAR_PATTERN_STR + r"\))")

    split_paras: List[DocParagraph] = []
    
    for p in merged_paras:
        temp_list = [p]
        
        def apply_split(p_list, regex, sub_repl=None, is_split_func=False):
            res = []
            for item in p_list:
                if is_split_func:
                    parts = regex.split(item.text)
                else:
                    marked = regex.sub(sub_repl, item.text)
                    parts = marked.split('\n')
                
                for part in parts:
                    clean_part = part.strip()
                    if clean_part:
                        res.append(DocParagraph(clean_part, item.page))
            return res

        temp_list = apply_split(temp_list, split_page_range_re, sub_repl=r"\1\n")
        temp_list = apply_split(temp_list, split_zh_smart_re, sub_repl=r"\n\1")
        temp_list = apply_split(temp_list, split_en_re, is_split_func=True)
        temp_list = apply_split(temp_list, split_mashed_re, is_split_func=True)
        split_paras.extend(temp_list)

    items: List[ReferenceItem] = []
    current_text = ""
    current_page = 1
    
    for p in split_paras:
        if looks_like_new_item(p.text) and not should_force_append(current_text, p.text):
            if current_text:
                parsed = parse_reference_item(current_text, len(items), current_page)
                if parsed: items.append(parsed)
            current_text = p.text
            current_page = p.page
        else:
            if current_text:
                current_text += " " + p.text
            else:
                current_text = p.text
                current_page = p.page

    if current_text:
        parsed = parse_reference_item(current_text, len(items), current_page)
        if parsed: items.append(parsed)

    return items

def parse_reference_item(text: str, idx: int, page: int) -> Optional[ReferenceItem]:
    text_norm = normalize_text(text)
    
    ym = re.search(r"\((" + YEAR_PATTERN_STR + r")([- ]?[a-zA-Z])?\)", text_norm)
    ym_any = re.search(r"\(([^)]*(?:19|20)\d{2}[^)]*)\)", text_norm)
    year, pre, found = "", "", False
    
    if ym:
        year = norm_year(ym.group(1) + (ym.group(2) or ""))
        pre = text_norm[:ym.start()].strip()
        found = True
    elif ym_any:
        year = norm_year(ym_any.group(1))
        pre = text_norm[:ym_any.start()].strip()
        found = True
    else:
        ym_zh = re.search(r"(?:[,，\s])\s*(" + YEAR_PATTERN_STR + r")\s*[,，\.]", text_norm)
        if ym_zh:
            year = norm_year(ym_zh.group(1))
            pre = text_norm[:ym_zh.start()].strip()
            found = True
        else:
            ym_dot = re.search(r"(?:^|[\.\s])(" + YEAR_PATTERN_STR + r")\.", text_norm)
            if ym_dot:
                 year = norm_year(ym_dot.group(1))
                 pre = text_norm[:ym_dot.start()].strip()
                 if pre.endswith("."): pre = pre[:-1].strip()
                 found = True

    if not found: return None

    check_text = pre if pre else text_norm[:20]
    lang = "en" if is_english_author_token(check_text) else "zh"

    if lang == "en":
        m1 = re.match(r"^([" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s\.]*?),", pre)
        if m1:
            a1 = m1.group(1).strip()
            a2 = None
            m2 = re.search(r"(?:&|and)\s*([" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s\.]*?)(?:,|$)", pre)
            if m2: a2 = m2.group(1).strip()
            return ReferenceItem("en", a1, a2, year, text_norm, idx, page)
        
        if len(pre) < 100: 
             a1 = pre.strip()
             m2_alt = re.search(r"(?:&|and)\s*([A-Za-z][A-Za-z'\-\s\.]*)", pre)
             a2 = m2_alt.group(1).strip() if m2_alt else None
             if a2 and (a2 in a1): a1 = re.split(r"(?:&|and)", a1)[0].strip()
             return ReferenceItem("en", a1, a2, year, text_norm, idx, page)
        return None

    pre_clean = re.sub(r"[與和及&]", " ", pre)
    tokens = re.findall(r"[\u4e00-\u9fff]{1,10}", pre_clean)
    if not tokens: return None
    a1 = tokens[0].strip()
    a2 = tokens[-1].strip() if len(tokens) >= 2 else None
    return ReferenceItem("zh", a1, a2, year, text_norm, idx, page)

# -------------------------
# In-text citation parsing
# -------------------------

en_outside_author_year_re = re.compile(
    r"(?<![" + ENG_CHARS + r"])"
    r"([" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s]*?(?:,\s*[" + ENG_CHARS + r"]\.?)?)"
    r"(?:"
        r"(?:\s*,\s*[" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s]*?(?:,\s*[" + ENG_CHARS + r"]\.?)?)*"
        r"\s*(?:&|and|,\s*&|,\s*and)\s*"
        r"([" + ENG_CHARS + r"][" + ENG_CHARS + r"'\-\s]*?(?:,\s*[" + ENG_CHARS + r"]\.?)?)"
    r"|"
        r"\s+et\s+al\.?"
    r")?"
    r"\s*\(\s*(" + YEAR_PATTERN_STR + r"[- ]?[a-zA-Z]?)\s*\)"
)
zh_outside_author_year_re = re.compile(
    r"(?:(?<=[由如見以與及])|(?<=(?:參考|根據|採用|使用|利用))|(?<![\u4e00-\u9fff]))"
    r"((?![與及])[\u4e00-\u9fff][\u4e00-\u9fff]{1,3})"
    r"(?:"
        r"(?:[、]\s*[\u4e00-\u9fff]{1,10})*"
        r"\s*(?:[、]|&|與|和)\s*"
        r"([\u4e00-\u9fff]{1,10})"
    r"|"
        r"\s*(?:等人|等)"
    r")?"
    r"\s*\(\s*(" + YEAR_PATTERN_STR + r"[- ]?[a-zA-Z]?)\s*\)"
)
paren_group_re = re.compile(r"\((.+?)\)")
seg_year_re = re.compile(r"(.+?)[,，\s]+(" + YEAR_PATTERN_STR + r"[- ]?[a-zA-Z]?)$")
etal_re = re.compile(r"\bet\s+al\.?\b", flags=re.IGNORECASE)

def get_context(text: str, match_start: int, match_end: int, window: int = 50) -> str:
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    return "..." + text[start:end] + "..."

def clean_chinese_author(name: str) -> str:
    prefixes = ["參考", "根據", "由", "如", "見", "以", "採用", "使用", "利用", "與", "及"]
    for p in prefixes:
        if name.startswith(p) and len(name) > len(p) + 1: return name[len(p):]
    return name

def clean_english_author_prefix(name: str) -> str:
    stopwords = ["as ", "see ", "in ", "by ", "cf ", "and "]
    name_lower = name.lower()
    for sw in stopwords:
        if name_lower.startswith(sw): return name[len(sw):].strip()
    return name

def is_valid_english_author(name: str) -> bool:
    if len(name.split()) > 5: return False
    return any(c.isupper() for c in name)

def fix_sticky_year_spacing(text: str) -> str:
    return re.sub(r"([a-zA-Z,，\.])([12]\d{3})", r"\1 \2", text)

def count_parens_balance(text: str) -> int:
    return (text.count('(') + text.count('（')) - (text.count(')') + text.count('）'))

def merge_broken_paragraphs(paragraphs: List[DocParagraph]) -> List[DocParagraph]:
    merged = []
    current_buf = ""
    current_page = 1
    balance = 0
    buffer_line_count = 0
    
    year_start_re = re.compile(r"^\s*\(" + YEAR_PATTERN_STR)
    ends_with_connector_re = re.compile(r"(?:,|and|&)\s*$", re.IGNORECASE)
    
    for p in paragraphs:
        p_str = str(p.text)
        
        if not current_buf:
            current_buf = p_str
            current_page = p.page
            balance = count_parens_balance(p_str)
            buffer_line_count = 1
        else:
            should_merge = False
            if balance > 0: should_merge = True
            elif year_start_re.match(p_str):
                clean = current_buf.rstrip()
                if clean and clean[-1] not in ".?!;。？！；": should_merge = True
            elif current_buf.strip().endswith("-") or current_buf.strip().endswith("–"):
                should_merge = True
            elif ends_with_connector_re.search(current_buf):
                should_merge = True

            if should_merge and buffer_line_count < 10:
                if current_buf.strip().endswith("-") or current_buf.strip().endswith("–"):
                    current_buf = current_buf.strip()[:-1] + p_str
                else:
                    current_buf += " " + p_str
                balance += count_parens_balance(p_str)
                buffer_line_count += 1
            else:
                merged.append(DocParagraph(current_buf, current_page))
                current_buf = p_str
                current_page = p.page
                balance = count_parens_balance(p_str)
                buffer_line_count = 1
            
    if current_buf:
        merged.append(DocParagraph(current_buf, current_page))
    return merged

def extract_intext_citations(paragraphs: List[DocParagraph], known_refs: List[ReferenceItem] = None) -> List[InTextCitation]:
    processed_paragraphs = merge_broken_paragraphs(paragraphs)
    results: List[InTextCitation] = []
    found_ranges: Set[Tuple[int, int, int]] = set()

    for i, p in enumerate(processed_paragraphs):
        p_norm = normalize_text(p.text)
        if not p_norm: continue
        p_norm = fix_sticky_year_spacing(p_norm)
        
        # 捕捉當前段落的頁碼
        curr_page = p.page

        # Helper to append
        def add_res(lang, a1, a2, y, raw_txt, p_idx, context):
            results.append(InTextCitation(lang, a1, a2, y, raw_txt, p_idx, context, curr_page))

        # English Outside
        for m in en_outside_author_year_re.finditer(p_norm):
            raw_a1 = m.group(1).strip()
            a1 = clean_english_author_prefix(raw_a1)
            if not is_valid_english_author(a1): continue
            found_ranges.add((i, m.start(), m.end()))
            a2 = m.group(2).strip() if m.group(2) else None
            y = m.group(3)
            ctx = get_context(p_norm, m.start(), m.end())
            if etal_re.search(m.group(0)): add_res("en", a1, None, y, m.group(0), i, ctx)
            else: add_res("en", a1, a2, y, m.group(0), i, ctx)

        # Chinese Outside
        for m in zh_outside_author_year_re.finditer(p_norm):
            raw_a1 = re.sub(r"(?:等人|等)$", "", m.group(1).strip())
            a1 = clean_chinese_author(raw_a1)
            found_ranges.add((i, m.start(), m.end()))
            a2 = m.group(2).strip() if m.group(2) else None
            y = m.group(3)
            ctx = get_context(p_norm, m.start(), m.end())
            add_res("zh", a1, a2, y, m.group(0), i, ctx)

        # Parentheses Groups
        for m_group in paren_group_re.finditer(p_norm):
            g = m_group.group(1).strip()
            if not g: continue
            group_ctx = get_context(p_norm, m_group.start(), m_group.end())
            
            has_semi = bool(re.search(CITATION_LIST_SEP_PATTERN, g))
            years_in = re.findall(YEAR_PATTERN_STR + r"[- ]?[a-zA-Z]?", g)
            
            if has_semi: parts = re.split(CITATION_LIST_SEP_PATTERN, g)
            elif len(years_in) >= 2:
                matches = list(re.finditer(r"(.+?)(?:[,，\s]+)(" + YEAR_PATTERN_STR + r"[- ]?[a-zA-Z]?)(?:[,，]|$)", g))
                parts = [m.group(0).strip(" ,，") for m in matches] if matches else re.split(CITATION_SECONDARY_SEP_PATTERN, g)
            else: parts = [g]

            for part in parts:
                seg = part.strip()
                if not seg: continue
                m = seg_year_re.match(seg)
                if not m: continue
                auth_part, year = m.group(1).strip(), m.group(2)
                
                if is_english_author_token(auth_part):
                    auth_part = clean_english_author_prefix(auth_part)
                    if not is_valid_english_author(auth_part): continue
                    found_ranges.add((i, m_group.start(), m_group.end()))
                    
                    if etal_re.search(auth_part):
                        add_res("en", auth_part.split()[0], None, year, seg, i, group_ctx)
                    elif "&" in auth_part or re.search(r"\band\b", auth_part, re.I):
                        parts2 = re.split(r"&|\band\b", auth_part, 1)
                        if len(parts2) == 2: add_res("en", parts2[0].strip(), parts2[1].strip(), year, seg, i, group_ctx)
                    else:
                        add_res("en", auth_part, None, year, seg, i, group_ctx)
                else:
                    found_ranges.add((i, m_group.start(), m_group.end()))
                    if re.search(r"(等人|等)", auth_part):
                        add_res("zh", re.sub(r"(等人|等)", "", auth_part).strip(), None, year, seg, i, group_ctx)
                    elif re.search(r"[、&與和]", auth_part):
                        tks = re.sub(r"[、&與和]", " ", auth_part).split()
                        if tks: add_res("zh", tks[0].strip(), tks[-1].strip() if len(tks)>1 else None, year, seg, i, group_ctx)
                    else:
                        add_res("zh", auth_part, None, year, seg, i, group_ctx)
                        
        # Reverse Search
        if known_refs and ("(" in p_norm or "（" in p_norm):
            for m_group in paren_group_re.finditer(p_norm):
                content = m_group.group(1) 
                g_start, g_end = m_group.start(), m_group.end()
                parts = re.split(CITATION_LIST_SEP_PATTERN if re.search(CITATION_LIST_SEP_PATTERN, content) else r"[,，]", content)
                for part in parts:
                    clean = part.strip()
                    if not clean: continue
                    for r in known_refs:
                        s_name = (r.author1.split(",")[0] if "," in r.author1 else r.author1.split()[0]) if r.lang=='en' else r.author1
                        if len(s_name)<2: continue
                        if s_name in clean and r.year in clean:
                            is_overlap = False
                            for (ex_i, ex_s, ex_e) in found_ranges:
                                if ex_i == i and g_start >= ex_s and g_end <= ex_e: 
                                    is_overlap = True
                                    break
                            if not is_overlap:
                                add_res(r.lang, s_name, None, r.year, clean, i, get_context(p_norm, g_start, g_end))
    
    unique_results = []
    seen = set()
    for res in results:
        key = (res.para_idx, res.author1.lower().replace(" ", ""), res.year)
        if key not in seen:
            unique_results.append(res)
            seen.add(key)
    return unique_results

# -------------------------
# Search Logic 
# -------------------------

def search_ref_in_text(raw_text: str, citation: InTextCitation) -> bool:
    raw_norm = normalize_text(raw_text).lower()
    auth1 = citation.author1.lower()
    year = citation.year.lower()
    return (auth1 in raw_norm or auth1.replace("-", " ") in raw_norm) and year in raw_norm

# -------------------------
# Matching
# -------------------------

def build_reference_index(refs: List[ReferenceItem]) -> Dict[Tuple[str, str, str], List[ReferenceItem]]:
    idx: Dict[Tuple[str, str, str], List[ReferenceItem]] = {}
    for r in refs:
        rk = reference_key(r)
        idx.setdefault((rk[0], rk[1], rk[3]), []).append(r)
    return idx

def match_citations_to_refs(citations: List[InTextCitation], refs: List[ReferenceItem], raw_ref_paras: List[DocParagraph]):
    ref_idx = build_reference_index(refs)
    matched_rows, missing_rows = [], []
    matched_ref_ids = set()
    
    refs_by_year = {}
    for r in refs:
        refs_by_year.setdefault(r.year, []).append(r)
        
    full_ref_text = "\n".join([p.text for p in raw_ref_paras])

    for c in citations:
        c_k = citation_key(c)
        key = (c_k[0], c_k[1], c_k[3])
        
        base_row = {
            "citation_raw": c.raw,
            "lang": c.lang,
            "author1": c.author1,
            "year": c.year,
            "para_idx": c.para_idx,
            "context": c.context,
            "page": c.page # 正文引用頁碼
        }

        # A. Exact
        if key in ref_idx:
            cands = ref_idx[key]
            for r in cands: matched_ref_ids.add(r.item_idx)
            row = base_row.copy()
            row.update({
                "match_type": "Exact",
                "ref_raw": cands[0].raw,
                "ref_page": cands[0].page # 參考文獻頁碼
            })
            matched_rows.append(row)
            continue
            
        # B. Raw Text Search
        if search_ref_in_text(full_ref_text, c):
             row = base_row.copy()
             row.update({
                "match_type": "Found in Raw Text (Parser Missed)",
                "ref_raw": "(Located in Reference Section text)",
                "ref_page": 0 
            })
             matched_rows.append(row)
             continue
        
        # D. Fuzzy
        final_cands = []
        if c.year in refs_by_year:
            for r in refs_by_year[c.year]:
                rk = reference_key(r)
                if rk[0] != c.lang: continue
                is_match = False
                if c.author2 and rk[2] and (c.author2 == rk[2] or is_similar_str(c.author2, rk[2])): is_match = True
                if c.author1 in r.raw: is_match = True
                
                if is_match:
                    ctx_norm = remove_accents(normalize_text(c.context).lower())
                    clean_a1 = rk[1]
                    if any(v in ctx_norm for v in [clean_a1, clean_a1.replace("-"," ")]):
                        matched_ref_ids.add(r.item_idx)
                        final_cands.append(r)
                        row = base_row.copy()
                        row.update({
                            "match_type": "Context Recovery",
                            "ref_raw": r.raw,
                            "ref_page": r.page
                        })
                        matched_rows.append(row)
                        break 
        if final_cands: continue
        
        missing_rows.append(base_row)

    uncited_rows = []
    for r in refs:
        if r.item_idx not in matched_ref_ids:
            uncited_rows.append({
                "文獻索引": r.item_idx,
                "語言": r.lang,
                "第一作者": r.author1,
                "年份": r.year,
                "參考文獻原文": r.raw,
                "page": r.page
            })

    return (
        pd.DataFrame(matched_rows),
        pd.DataFrame(missing_rows),
        pd.DataFrame(uncited_rows),
    )

def run_check_from_file_bytes(file_bytes: bytes, file_type: str):
    if file_type == "docx":
        paragraphs = read_docx_bytes(file_bytes)
    elif file_type == "pdf":
        paragraphs = read_pdf_bytes(file_bytes)
    else:
        raise ValueError("不支援的檔案格式")

    ref_start = find_reference_section_start(paragraphs)
    if ref_start is None:
        raise ValueError("找不到參考文獻標題。")

    body_paras = paragraphs[:ref_start]
    ref_paras_raw = paragraphs[ref_start:] 
    
    refs = extract_reference_items(paragraphs, ref_start)
    citations = extract_intext_citations(body_paras, known_refs=refs)
    
    matched_df, missing_df, uncited_df = match_citations_to_refs(citations, refs, ref_paras_raw)

    summary_df = pd.DataFrame([{
        "正文段落數": len(body_paras),
        "偵測到的參考文獻項目數": len(refs),
        "提取出的正文引用數": len(citations),
        "成功配對數": len(matched_df),
        "缺失引用數 (正文有/文末無)": len(missing_df),
        "未引用文獻數 (文末有/正文無)": len(uncited_df),
    }])

    return summary_df, matched_df, missing_df, uncited_df
