import re
from collections import defaultdict
import unicodedata

_SPLIT_YEAR_TOKEN = r"(?:19\d{2}[a-z]?|20\d{2}[a-z]?|n\s*\.\s*d\s*\.?|no\s+date|in\s+press|\u5370\u5237\u4e2d|\u672a\u520a)"
_YEAR_PATTERN = re.compile(
    r"(?:\b(?:19\d{2}[a-z]?|20\d{2}[a-z]?|no\s+date|in\s+press)\b|n\s*\.\s*d\s*\.?|\u5370\u5237\u4e2d|\u672a\u520a)",
    re.IGNORECASE,
)
_YEAR_TOKEN_PATTERN = re.compile(r"\(\s*(19\d{2}|20\d{2})\s*([a-z]?)\s*\)|\b(19\d{2}|20\d{2})([a-z]?)\b", re.IGNORECASE)
_AUTHOR_WITH_YEAR_PATTERN = (
    rf"(?:"
    rf"[A-Z][A-Za-z'\-]+(?:\s+(?:[A-Z][A-Za-z'\-]+|[a-z]{{1,5}})){{0,3}}(?:,\s*[A-Z](?:\.[A-Z])*\.)?"
    rf"|"
    rf"[\u4e00-\u9fff]{{1,20}}"
    rf")\s*[\(\uff08]\s*{_SPLIT_YEAR_TOKEN}\s*[\)\uff09]"
)
_AUTHOR_START_PATTERN = re.compile(rf"^{_AUTHOR_WITH_YEAR_PATTERN}", re.IGNORECASE)
_INITIALS_PATTERN = re.compile(r"^(?:[A-Z]\.)+(?:\s*[A-Z]\.)*$", re.IGNORECASE)
_INLINE_REF_SPLIT_PATTERN = re.compile(
    rf"(?<=[\.;\u3002\uff1b])\s+(?={_AUTHOR_WITH_YEAR_PATTERN})",
    re.IGNORECASE,
)
_REFERENCE_START_YEAR_TOKEN = r"(?:\d{4}[a-z]?|n\s*[\.\u3002]\s*d\s*[\.\u3002]?|in\s+press)"
_REFERENCE_START_EN_STRICT_PATTERN = re.compile(
    rf"[A-Z][A-Za-z'’\-]+,\s*(?:[A-Z]\.\s*)+"
    rf"(?:,\s*[A-Z][A-Za-z'’\-]+,\s*(?:[A-Z]\.\s*)+)*"
    rf"(?:\s*(?:&|and)\s*[A-Z][A-Za-z'’\-]+,\s*(?:[A-Z]\.\s*)+)?"
    rf"\s*[\(\uff08]\s*{_REFERENCE_START_YEAR_TOKEN}\s*[\)\uff09]",
    re.IGNORECASE,
)
_REFERENCE_START_EN_RELAXED_PATTERN = re.compile(
    rf"[A-Z][A-Za-z'’\-]+,\s*[^()]{{0,220}}?"
    rf"[\(\uff08]\s*{_REFERENCE_START_YEAR_TOKEN}\s*[\)\uff09]",
    re.IGNORECASE,
)
_REFERENCE_START_ZH_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,20}\s*[\(\uff08]\s*\d{4}[a-z]?\s*[\)\uff09]",
    re.IGNORECASE,
)
_REFERENCE_START_DETECTION_TRANSLATION = str.maketrans({
    "（": "(",
    "）": ")",
    "，": ",",
    "．": ".",
    "。": ".",
    "：": ":",
    "；": ";",
    "－": "-",
    "–": "-",
    "—": "-",
    "‒": "-",
    "―": "-",
    "\u3000": " ",
})
_REFERENCE_PARSE_DETECTION_TRANSLATION = str.maketrans({
    "（": "(",
    "）": ")",
    "．": ".",
    "。": ".",
    "，": ",",
    "\u3000": " ",
})
_SAFE_NORMALIZE_TRANSLATION = str.maketrans({
    "（": "(",
    "）": ")",
    "，": ",",
    "。": ".",
    "：": ":",
    "；": ";",
    "－": "-",
    "–": "-",
    "—": "-",
})
_PAREN_YEAR_TOKEN_PATTERN = re.compile(
    r"[\(\uff08]\s*(?:(?P<year>(?:19|20)\d{2})(?P<suffix>[a-z]?)|(?P<nd>n\s*\.\s*d\s*\.?)|(?P<in_press>in\s+press))\s*[\)\uff09]",
    re.IGNORECASE,
)
_CHINESE_AUTHOR_WITH_NUMERIC_YEAR_START_PATTERN = re.compile(
    r"^\s*(?P<author>[\u4e00-\u9fff]{1,20})\s*[\(\uff08]\s*(?:19|20)\d{2}[a-z]?\s*[\)\uff09]",
    re.IGNORECASE,
)
_CITATION_YEAR_TOKEN_PATTERN = r"(?:\d{4}[a-z]?|n\s*\.\s*d\s*\.?|in\s+press)"
_PARENTHETICAL_CITATION_BLOCK_PATTERN = re.compile(r"[\(\uff08]([^()\uff08\uff09]{1,240})[\)\uff09]")
_PARENTHETICAL_CITATION_SEGMENT_LOCATOR_PATTERN = re.compile(
    rf"^.+?[,\uff0c]\s*{_CITATION_YEAR_TOKEN_PATTERN}"
    rf"(?:\s*[,，]\s*(?:p|pp)\.?\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*$",
    re.IGNORECASE,
)
_PARENTHETICAL_CITATION_SEGMENT_PATTERN = re.compile(
    rf"^.+?[,\uff0c]\s*{_CITATION_YEAR_TOKEN_PATTERN}\s*$",
    re.IGNORECASE,
)
_NARRATIVE_CITATION_PATTERN = re.compile(
    rf"\b([A-Z][A-Za-z'’\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’\-]+|\s+et\s+al\.)?)"
    rf"\s*[\(\uff08]\s*({_CITATION_YEAR_TOKEN_PATTERN})\s*[\)\uff09]",
    re.IGNORECASE,
)
_NARRATIVE_CHINESE_CITATION_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{1,10})\s*[\(\uff08]\s*(\d{4})\s*[\)\uff09]",
    re.IGNORECASE,
)
_CITATION_AUTHOR_YEAR_PAREN_PATTERN = re.compile(
    rf"^\s*(?P<author>.+?)\s*[\(\uff08]\s*(?P<token>{_CITATION_YEAR_TOKEN_PATTERN})\s*[\)\uff09]\s*$",
    re.IGNORECASE,
)
_CITATION_AUTHOR_YEAR_COMMA_PATTERN = re.compile(
    rf"^\s*(?P<author>.+?)\s*[,，]\s*(?P<token>{_CITATION_YEAR_TOKEN_PATTERN})\s*$",
    re.IGNORECASE,
)
_CITATION_YEAR_TOKEN_EXTRACT_PATTERN = re.compile(
    rf"(?P<year>(?:19|20)\d{{2}})(?P<suffix>[a-z]?)|(?P<nd>n\s*\.\s*d\s*\.?)|(?P<in_press>in\s+press)",
    re.IGNORECASE,
)
_CITATION_SEGMENT_TRANSLATION = str.maketrans({
    "（": "(",
    "）": ")",
    "，": ",",
    "；": ";",
    "。": ".",
    "－": "-",
    "–": "-",
    "—": "-",
    "\u3000": " ",
})


def _build_match_key_token(year: int | str | None, year_suffix: str | None, year_token_type: str | None) -> str:
    if isinstance(year, int):
        return f"{year}{(year_suffix or '').strip().lower()}"

    year_str = (str(year).strip() if year is not None else "")
    if year_str.isdigit():
        return f"{year_str}{(year_suffix or '').strip().lower()}"

    token_type = (year_token_type or "").strip().lower()
    if token_type == "n.d.":
        return "nd"
    if token_type == "in_press":
        return "inpress"
    return "missing"


def _normalize_person_key_name(name: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", (name or "").strip().lower())
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)
    return normalized


def build_reference_key(
    first_author_surname: str | dict,
    year: str | int | None = None,
    year_suffix: str | None = None,
    title_fragment: str | None = None,
) -> str:
    # Backward-compatible extension:
    # - legacy mode: build_reference_key(surname, year, suffix, title_fragment)
    # - matching mode: build_reference_key(parsed_ref_dict)
    if isinstance(first_author_surname, dict) and year is None and year_suffix is None and title_fragment is None:
        parsed_ref = first_author_surname
        surname_key = _normalize_person_key_name(parsed_ref.get("first_author_surname") or parsed_ref.get("surname"))
        if not surname_key:
            return ""
        year_token = _build_match_key_token(
            parsed_ref.get("year"),
            parsed_ref.get("year_suffix"),
            parsed_ref.get("year_token_type"),
        )
        return f"{surname_key}_{year_token}"

    surname = re.sub(r"[^a-z0-9]", "", (first_author_surname or "").lower())
    year_token = f"{(year or '').strip()}{(year_suffix or '').strip().lower()}"
    if not surname or not year_token:
        return ""

    base = f"{surname}_{year_token}"
    if not title_fragment:
        return base

    title_clean = re.sub(r"[^a-z0-9]", "", title_fragment.lower())
    if not title_clean:
        return base

    return f"{base}_{title_clean[:12]}"


def _normalize_reference_text(text: str) -> str:
    normalized = " ".join((text or "").split())
    normalized = re.sub(r"\s+,", ",", normalized)
    normalized = re.sub(r",\s*", ", ", normalized)
    normalized = re.sub(r"\s+\.", ".", normalized)
    normalized = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", "–", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def safe_normalize_reference_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.translate(_SAFE_NORMALIZE_TRANSLATION)

    normalized_lines = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", raw_line.strip())
        line = re.sub(r"\s+([,.;:])", r"\1", line)
        line = re.sub(r"\(\s+", "(", line)
        line = re.sub(r"\s+\)", ")", line)
        line = re.sub(r"([,.;:])\s+", r"\1 ", line)
        line = re.sub(r"\s+", " ", line).strip()
        normalized_lines.append(line)

    collapsed_lines = []
    prev_blank = False
    for line in normalized_lines:
        if line == "":
            if prev_blank:
                continue
            prev_blank = True
            collapsed_lines.append("")
            continue
        prev_blank = False
        collapsed_lines.append(line)

    return "\n".join(collapsed_lines)


def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.translate(str.maketrans({
        "。": ".",
        "、": ",",
        "；": ";",
        "：": ":",
    }))
    normalized = normalized.replace("–", "-").replace("—", "-").replace("－", "-")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    lines = []
    for line in normalized.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        lines.append(line)
    return "\n".join(lines)


def _normalize_for_reference_start_detection(text: str) -> str:
    # Keep this normalization minimal and 1:1 where possible so start indices stay usable.
    return (text or "").translate(_REFERENCE_START_DETECTION_TRANSLATION)


def _is_reference_start_boundary(text: str, idx: int) -> bool:
    if idx <= 0:
        return True

    cursor = idx - 1
    while cursor >= 0 and text[cursor] in (" ", "\t"):
        cursor -= 1
    if cursor < 0:
        return True

    if text[cursor] == "\n":
        previous_line_start = text.rfind("\n", 0, cursor)
        previous_line = text[previous_line_start + 1:cursor].strip()
        if re.search(r"(?:&|\band\b|,)\s*$", previous_line, re.IGNORECASE):
            return False
        return True

    # Prefer hard sentence boundaries to avoid splitting on in-sentence year mentions.
    if text[cursor] in ".;!?":
        return True

    # Allow URL tails as practical boundaries in noisy merged lines.
    token_start = cursor
    while token_start >= 0 and text[token_start] not in (" ", "\t", "\n"):
        token_start -= 1
    prev_token = text[token_start + 1:cursor + 1].lower()
    if "http://" in prev_token or "https://" in prev_token:
        return True

    return False


def _find_reference_starts(text: str) -> list[int]:
    detection_text = _normalize_for_reference_start_detection(text)
    if not detection_text.strip():
        return []

    candidates = set()
    patterns = (
        _REFERENCE_START_EN_STRICT_PATTERN,
        _REFERENCE_START_EN_RELAXED_PATTERN,
        _REFERENCE_START_ZH_PATTERN,
    )
    for pattern in patterns:
        for match in pattern.finditer(detection_text):
            start_idx = match.start()
            if not _is_reference_start_boundary(detection_text, start_idx):
                continue
            candidates.add(start_idx)

    starts = sorted(candidates)

    # Merge near-duplicate starts from strict/relaxed patterns.
    deduped = []
    for start_idx in starts:
        if deduped and start_idx - deduped[-1] < 8:
            continue
        deduped.append(start_idx)
    return deduped


def _split_references(raw_text: str) -> list[str]:
    text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    def _looks_like_new_reference_start(line: str) -> bool:
        stripped = line.strip()
        if _AUTHOR_START_PATTERN.search(stripped) is not None:
            return True
        return re.search(
            rf"^[A-Z\u4e00-\u9fff][^()\n]{{0,100}}[\(\uff08]\s*{_SPLIT_YEAR_TOKEN}\s*[\)\uff09]",
            stripped,
            re.IGNORECASE,
        ) is not None

    def _is_incomplete_tail(line: str) -> bool:
        tail = (line or "").strip()
        if not tail:
            return True
        if re.search(r"(?:,|;|:|&|\band\b|-|–|—)\s*$", tail, re.IGNORECASE):
            return True
        return re.search(r"[.!?。！？]\s*$", tail) is None

    def _merge_wrapped_lines(lines: list[str]) -> list[str]:
        merged = []
        for line in lines:
            normalized_line = re.sub(r"\s+", " ", line.strip())
            if not normalized_line:
                continue
            if not merged:
                merged.append(normalized_line)
                continue

            if _looks_like_new_reference_start(normalized_line):
                merged.append(normalized_line)
                continue

            prev = merged[-1]
            if _is_incomplete_tail(prev) or not _looks_like_new_reference_start(normalized_line):
                merged[-1] = f"{prev} {normalized_line}".strip()
            else:
                merged.append(normalized_line)
        return merged

    def _split_inline_reference_segments(line: str) -> list[str]:
        normalized_line = re.sub(r"\s+", " ", line.strip())
        if not normalized_line:
            return []
        segments = [part.strip() for part in _INLINE_REF_SPLIT_PATTERN.split(normalized_line) if part.strip()]
        return segments or [normalized_line]

    def _split_lines_by_fallback(lines: list[str]) -> list[str]:
        items = []
        current_lines = []

        expanded_lines = []
        for line in _merge_wrapped_lines(lines):
            expanded_lines.extend(_split_inline_reference_segments(line))

        for line in expanded_lines:
            if not current_lines:
                current_lines = [line]
                continue

            current_text = " ".join(current_lines)
            current_has_year = _YEAR_PATTERN.search(current_text) is not None
            line_has_year = _YEAR_PATTERN.search(line) is not None
            line_looks_like_author_start = _AUTHOR_START_PATTERN.search(line) is not None

            if current_has_year and (line_has_year or line_looks_like_author_start):
                items.append(" ".join(current_lines))
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            items.append(" ".join(current_lines))
        return items

    lines_raw = text.split("\n")
    has_blank_line = any(not line.strip() for line in lines_raw)

    if has_blank_line:
        blocks = []
        current_block = []
        for line in lines_raw:
            if line.strip():
                current_block.append(line)
            elif current_block:
                blocks.append(current_block)
                current_block = []
        if current_block:
            blocks.append(current_block)

        if len(blocks) > 1:
            items = []
            for block_lines in blocks:
                normalized_lines = [re.sub(r"\s+", " ", line.strip()) for line in block_lines if line.strip()]
                if not normalized_lines:
                    continue
                merged_lines = _merge_wrapped_lines(normalized_lines)

                # Keep blank-line segmentation as primary when multiple blocks already exist.
                if not any(_YEAR_PATTERN.search(line) for line in normalized_lines):
                    # For no-year blocks, only merge when the block still looks like one wrapped reference.
                    if (
                        len(normalized_lines) > 1
                        and len(merged_lines) == 1
                        and re.search(r",\s*[A-Za-z\u4e00-\u9fff]", merged_lines[0])
                        and re.search(r"[\(\uff08].*[\)\uff09]", merged_lines[0])
                    ):
                        items.extend(merged_lines)
                    else:
                        items.extend(normalized_lines)
                else:
                    items.append(" ".join(merged_lines))
            return items

        if len(blocks) == 1:
            normalized_lines = [re.sub(r"\s+", " ", line.strip()) for line in blocks[0] if line.strip()]
            if not normalized_lines:
                return []

            # Single block with no year clues: keep line-level split (A\nB\n\nC -> A,B,C).
            if not any(_YEAR_PATTERN.search(line) for line in normalized_lines):
                return normalized_lines

            return _split_lines_by_fallback(normalized_lines)

        return []

    lines = [re.sub(r"\s+", " ", line.strip()) for line in lines_raw if line.strip()]
    if not lines:
        return []
    return _split_lines_by_fallback(lines)


def split_reference_items(raw_text: str) -> list[str]:
    normalized_text = normalize_text(raw_text)
    fallback_items = _split_references(normalized_text)

    # Prefer explicit start-detection splitting when we can find multiple starts.
    starts = _find_reference_starts(normalized_text)
    if len(starts) >= 2:
        start_split_items = []
        boundaries = starts + [len(normalized_text)]
        for idx, start in enumerate(starts):
            piece = normalized_text[start:boundaries[idx + 1]]
            cleaned = re.sub(r"\s+", " ", piece).strip()
            if cleaned:
                start_split_items.append(cleaned)

        # Keep fallback as default; only use start split when it clearly finds more boundaries.
        if len(start_split_items) >= 2 and len(start_split_items) > len(fallback_items):
            return start_split_items

    # Fallback keeps legacy behavior (blank-line and year-clue based splitting).
    return fallback_items


def _normalize_for_parse_detection(text: str) -> str:
    return (text or "").translate(_REFERENCE_PARSE_DETECTION_TRANSLATION)


def _extract_authors_raw(item_text: str, year_match: re.Match[str] | None) -> str:
    if year_match is not None:
        return item_text[: year_match.start()].strip()

    period_positions = [pos for pos in (item_text.find("."), item_text.find("。")) if pos != -1]
    if period_positions:
        return item_text[: min(period_positions)].strip()

    return item_text[:120].strip()


def _normalize_author_piece(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_first_author_surname(item_text: str, authors_raw: str) -> tuple[str | None, str]:
    chinese_match = _CHINESE_AUTHOR_WITH_NUMERIC_YEAR_START_PATTERN.match(item_text or "")
    if chinese_match:
        author = _normalize_author_piece(chinese_match.group("author"))
        if author:
            return author, "high"

    normalized_authors = _normalize_author_piece(authors_raw).strip(",，;；")
    if not normalized_authors:
        return None, "low"

    if "," in normalized_authors or "，" in normalized_authors:
        surname = re.split(r"[,，]", normalized_authors, maxsplit=1)[0].strip()
        surname = _normalize_author_piece(surname).rstrip(".;:，, ")
        if surname:
            return surname, "high"
        return None, "low"

    fallback = _normalize_author_piece(normalized_authors[:40])
    if fallback:
        return fallback, "low"
    return None, "low"


def _parse_parenthesized_year_token(detection_text: str) -> tuple[re.Match[str] | None, int | None, str | None, str]:
    match = _PAREN_YEAR_TOKEN_PATTERN.search(detection_text or "")
    if not match:
        return None, None, None, "missing"

    if match.group("year"):
        year = int(match.group("year"))
        suffix = (match.group("suffix") or "").lower() or None
        return match, year, suffix, "year"

    if match.group("nd"):
        return match, None, None, "n.d."

    if match.group("in_press"):
        return match, None, None, "in_press"

    return match, None, None, "missing"


def parse_reference_item(item: str) -> dict:
    raw_item = "" if item is None else str(item)
    item_text = raw_item.strip()
    detection_text = _normalize_for_parse_detection(item_text)

    year_match, year, year_suffix, year_token_type = _parse_parenthesized_year_token(detection_text)
    authors_raw = _extract_authors_raw(item_text, year_match)
    first_author_surname, surname_confidence = _extract_first_author_surname(item_text, authors_raw)

    return {
        "raw": raw_item,
        "authors_raw": authors_raw,
        "first_author_surname": first_author_surname,
        "surname_confidence": surname_confidence,
        "year": year,
        "year_suffix": year_suffix,
        "year_token_type": year_token_type,
    }


def _normalize_citation_segment_for_match(seg: str) -> str:
    normalized = unicodedata.normalize("NFKC", seg or "")
    normalized = normalized.translate(_CITATION_SEGMENT_TRANSLATION)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _looks_like_parenthetical_citation_segment(seg: str) -> bool:
    normalized_seg = _normalize_citation_segment_for_match(seg)
    if not normalized_seg:
        return False
    return (
        _PARENTHETICAL_CITATION_SEGMENT_LOCATOR_PATTERN.match(normalized_seg) is not None
        or _PARENTHETICAL_CITATION_SEGMENT_PATTERN.match(normalized_seg) is not None
    )


def extract_citations(text: str) -> list[dict]:
    raw_text = "" if text is None else str(text)
    citations = []

    for block_match in _PARENTHETICAL_CITATION_BLOCK_PATTERN.finditer(raw_text):
        block_content = block_match.group(1)
        for segment in re.split(r"[;；]", block_content):
            candidate = _normalize_citation_segment_for_match(segment)
            if not candidate:
                continue
            if _looks_like_parenthetical_citation_segment(candidate):
                citations.append({"raw": candidate, "style": "parenthetical"})

    for match in _NARRATIVE_CITATION_PATTERN.finditer(raw_text):
        author_part = match.group(1).strip()
        year_token = match.group(2).strip()
        citations.append({"raw": f"{author_part} ({year_token})", "style": "narrative"})

    for match in _NARRATIVE_CHINESE_CITATION_PATTERN.finditer(raw_text):
        author_part = match.group(1).strip()
        year_token = match.group(2).strip()
        citations.append({"raw": f"{author_part} ({year_token})", "style": "narrative_zh"})

    # Keep order, deduplicate equivalent raw forms.
    deduped = []
    seen = set()
    for citation in citations:
        raw = str(citation.get("raw", ""))
        key = re.sub(r"\s+", " ", raw).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


def _parse_citation_year_token(text: str) -> tuple[int | None, str | None, str]:
    matches = list(_CITATION_YEAR_TOKEN_EXTRACT_PATTERN.finditer(text or ""))
    if not matches:
        return None, None, "missing"

    match = matches[-1]
    if match.group("year"):
        year = int(match.group("year"))
        suffix = (match.group("suffix") or "").lower() or None
        return year, suffix, "year"
    if match.group("nd"):
        return None, None, "n.d."
    if match.group("in_press"):
        return None, None, "in_press"
    return None, None, "missing"


def _extract_citation_author_part(text: str) -> str:
    normalized_text = (text or "").strip()

    m_paren = _CITATION_AUTHOR_YEAR_PAREN_PATTERN.match(normalized_text)
    if m_paren:
        return m_paren.group("author").strip()

    m_comma = _CITATION_AUTHOR_YEAR_COMMA_PATTERN.match(normalized_text)
    if m_comma:
        return m_comma.group("author").strip()

    year_match = _CITATION_YEAR_TOKEN_EXTRACT_PATTERN.search(normalized_text)
    if year_match:
        return normalized_text[: year_match.start()].strip(" ,，(")

    return normalized_text


def _extract_first_citation_surname(author_part: str) -> str | None:
    author = _normalize_author_piece(author_part)
    if not author:
        return None

    chinese_m = re.match(r"^([\u4e00-\u9fff]{1,20})", author)
    if chinese_m:
        return chinese_m.group(1)

    author = re.sub(r"\bet\s+al\.\s*$", "", author, flags=re.IGNORECASE).strip()
    first_author = re.split(r"\s+(?:and|&)\s+", author, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    first_author = re.split(r"[,，]", first_author, maxsplit=1)[0].strip()
    first_author = re.sub(r"[^A-Za-z0-9'’\-\s\u4e00-\u9fff]", "", first_author).strip()
    return first_author or None


def parse_citation(citation_str: str | dict) -> dict:
    if isinstance(citation_str, dict):
        raw = str(citation_str.get("raw", ""))
    else:
        raw = "" if citation_str is None else str(citation_str)

    normalized = _normalize_for_parse_detection(raw.strip())
    year, year_suffix, year_token_type = _parse_citation_year_token(normalized)
    author_part = _extract_citation_author_part(normalized)
    surname = _extract_first_citation_surname(author_part)

    return {
        "raw": raw,
        "surname": surname,
        "year": year,
        "year_suffix": year_suffix,
        "year_token_type": year_token_type,
    }


def build_citation_key(parsed_cite: dict) -> str:
    surname_key = _normalize_person_key_name((parsed_cite or {}).get("surname"))
    if not surname_key:
        return ""
    year_token = _build_match_key_token(
        (parsed_cite or {}).get("year"),
        (parsed_cite or {}).get("year_suffix"),
        (parsed_cite or {}).get("year_token_type"),
    )
    return f"{surname_key}_{year_token}"


def _preview_reference_raw(raw: str, limit: int = 120) -> str:
    compact = " ".join((raw or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def match_citations(text: str, reference_items: list[str]) -> dict:
    parsed_refs = [parse_reference_item(item) for item in (reference_items or [])]
    ref_index = defaultdict(list)
    for parsed_ref in parsed_refs:
        ref_key = build_reference_key(parsed_ref)
        if not ref_key:
            continue
        ref_index[ref_key].append(parsed_ref)
    ref_keys = set(ref_index.keys())

    extracted_citations = extract_citations(text)
    parsed_citations = [parse_citation(citation) for citation in extracted_citations]
    cite_keys = {build_citation_key(parsed_citation) for parsed_citation in parsed_citations}
    cite_keys.discard("")

    matched = []
    missing = []
    ambiguous = []
    used_ref_keys = set()

    for cite_key in sorted(cite_keys):
        candidates = ref_index.get(cite_key, [])
        if not candidates:
            missing.append(cite_key)
            continue

        used_ref_keys.add(cite_key)
        if len(candidates) == 1:
            matched.append(cite_key)
            continue

        ambiguous.append({
            "key": cite_key,
            "reason": "multiple_references_same_key",
            "candidates": [_preview_reference_raw(candidate.get("raw", "")) for candidate in candidates],
        })

    extra = sorted(ref_keys.difference(used_ref_keys))

    return {
        "matched": sorted(matched),
        "missing_in_reference": sorted(missing),
        "extra_in_reference": extra,
        "ambiguous": sorted(ambiguous, key=lambda item: item.get("key", "")),
    }


def debug_split_example() -> list[str]:
    sample = "A文獻\nB文獻\n\nC文獻"
    return _split_references(sample)


if __name__ == "__main__":
    demo_items = debug_split_example()
    print(f"count={len(demo_items)}")
    for i, item in enumerate(demo_items, start=1):
        print(f"{i}. {item}")


def _find_year_info(text: str):
    m = _YEAR_TOKEN_PATTERN.search(text)
    if not m:
        return None

    if m.group(1):
        year = m.group(1)
        suffix = (m.group(2) or "").lower()
        parenthesized = True
    else:
        year = m.group(3)
        suffix = (m.group(4) or "").lower()
        parenthesized = False

    return {
        "year": year,
        "year_suffix": suffix,
        "span": m.span(),
        "parenthesized": parenthesized,
    }


def _looks_like_initials(token: str) -> bool:
    t = (token or "").strip().replace(" ", "")
    if not t:
        return False
    return _INITIALS_PATTERN.match(t) is not None


def _parse_authors_from_raw(authors_raw: str) -> tuple[list[str], bool]:
    raw = (authors_raw or "").strip().strip(",")
    if not raw:
        return [], False

    normalized = re.sub(r"\s+(?:and|&)\s+", " & ", raw, flags=re.IGNORECASE)
    parts = [p.strip() for p in normalized.split(" & ") if p.strip()]
    if not parts:
        return [], False

    authors = []

    for part in parts:
        tokens = [t.strip() for t in part.split(",") if t.strip()]
        if not tokens:
            continue

        i = 0
        while i < len(tokens):
            surname = tokens[i].strip().strip(".")
            if not surname:
                i += 1
                continue

            if i + 1 < len(tokens) and _looks_like_initials(tokens[i + 1]):
                initials = tokens[i + 1].strip()
                authors.append(f"{surname}, {initials}")
                i += 2
            else:
                authors.append(surname)
                i += 1

    if not authors:
        fallback = raw.split(",")[0].strip().strip(".")
        if fallback:
            return [fallback], False
        return [], False

    return authors, True


def _extract_surname(author_text: str) -> str:
    text = (author_text or "").strip()
    if not text:
        return ""

    if "," in text:
        surname = text.split(",", 1)[0].strip()
    else:
        surname = text.split()[0].strip() if text.split() else ""

    surname = re.sub(r"[^A-Za-z0-9'\-\s]", "", surname).strip()
    return surname


def _apply_year_token(text: str, year: str, suffix: str) -> str:
    suffix = (suffix or "").lower()
    canonical = f"({year}{suffix})"

    parenthesized_pattern = rf"\(\s*{year}\s*[a-z]?\s*\)"
    updated, count = re.subn(parenthesized_pattern, canonical, text, count=1, flags=re.IGNORECASE)
    if count == 1:
        return updated

    bare_pattern = rf"\b{year}[a-z]?\b"
    updated, count = re.subn(bare_pattern, canonical, text, count=1, flags=re.IGNORECASE)
    if count == 1:
        return updated

    return text


def _extract_title_and_source(text: str):
    year_info = _find_year_info(text)
    if not year_info:
        return None, text.strip()

    rest = text[year_info["span"][1]:].strip()
    if rest.startswith("."):
        rest = rest[1:].strip()

    if not rest:
        return None, ""

    period_idx = rest.find(".")
    if period_idx == -1:
        return rest.strip(), ""

    title = rest[:period_idx].strip() or None
    source = rest[period_idx + 1 :].strip()
    return title, source


def _suffix_rank(suffix: str) -> tuple[int, str]:
    s = (suffix or "").lower()
    if not s:
        return (0, "")
    return (1, s)


def _build_group_key(item: dict):
    surnames = item["author_surnames"]
    year = item["fields"]["year"]
    first = item["fields"]["first_author_surname"].lower()

    if surnames and len(surnames) > 1:
        return ("authors", tuple(surnames), year)
    return ("first", first, year)


def _apply_auto_suffix(parsed_items: list[dict]) -> int:
    grouped = defaultdict(list)
    for item in parsed_items:
        grouped[_build_group_key(item)].append(item)

    auto_applied_count = 0

    for _, group_items in grouped.items():
        if len(group_items) <= 1:
            continue

        used = {it["fields"]["year_suffix"] for it in group_items if it["fields"]["year_suffix"]}
        next_code = ord("a")

        for item in group_items:
            if item["fields"]["year_suffix"]:
                continue

            while chr(next_code) in used and next_code <= ord("z"):
                next_code += 1

            if next_code > ord("z"):
                break

            assigned = chr(next_code)
            next_code += 1
            used.add(assigned)

            item["fields"]["year_suffix"] = assigned
            item["text"] = _apply_year_token(item["text"], item["fields"]["year"], assigned)
            item["warnings"].append("auto_suffix_applied")
            auto_applied_count += 1

    return auto_applied_count


def _finalize_item(item: dict):
    title_fragment, source_fragment = _extract_title_and_source(item["text"])
    item["fields"]["title_fragment"] = title_fragment
    item["fields"]["source_fragment"] = source_fragment

    key = build_reference_key(
        item["fields"]["first_author_surname"],
        item["fields"]["year"],
        item["fields"]["year_suffix"],
        title_fragment,
    )
    item["key"] = key

    title_key = re.sub(r"[^a-z0-9]", "", (title_fragment or "").lower())
    item["sort_key"] = (
        item["fields"]["first_author_surname"].lower(),
        tuple(item["author_surnames"][1:]),
        int(item["fields"]["year"]),
        _suffix_rank(item["fields"]["year_suffix"]),
        title_key,
        item["index"],
    )


def normalize_and_sort_references(raw_text: str) -> tuple[str, dict]:
    raw_items = _split_references(raw_text)

    parsed_items = []
    unparsed_items = []

    for idx, raw_item in enumerate(raw_items):
        text = _normalize_reference_text(raw_item)
        if not text:
            continue

        item = {
            "index": idx,
            "raw_text": raw_item,
            "text": text,
            "warnings": [],
            "fields": {
                "authors_raw": None,
                "authors_list": [],
                "first_author_surname": None,
                "year": None,
                "year_suffix": "",
                "title_fragment": None,
                "source_fragment": None,
            },
            "key": "",
            "author_surnames": [],
            "sort_key": None,
        }

        year_info = _find_year_info(text)
        if not year_info:
            item["warnings"].append("year_missing")
            unparsed_items.append(item)
            continue

        item["fields"]["year"] = year_info["year"]
        item["fields"]["year_suffix"] = year_info["year_suffix"]
        item["text"] = _apply_year_token(item["text"], year_info["year"], year_info["year_suffix"])

        authors_raw = text[: year_info["span"][0]].strip().rstrip(",.;")
        item["fields"]["authors_raw"] = authors_raw

        authors_list, author_parse_ok = _parse_authors_from_raw(authors_raw)
        if not author_parse_ok:
            item["warnings"].append("author_parse_failed")

        author_surnames = [_extract_surname(a).lower() for a in authors_list if _extract_surname(a)]

        first_author_surname = ""
        if author_surnames:
            first_author_surname = author_surnames[0]
        elif authors_raw:
            fallback = _extract_surname(authors_raw.split(",", 1)[0])
            first_author_surname = fallback.lower() if fallback else ""

        if not first_author_surname:
            item["warnings"].append("author_missing")
            unparsed_items.append(item)
            continue

        if not authors_list:
            authors_list = [first_author_surname]
            author_surnames = [first_author_surname]

        item["fields"]["authors_list"] = authors_list
        item["fields"]["first_author_surname"] = first_author_surname
        item["author_surnames"] = author_surnames

        _finalize_item(item)
        parsed_items.append(item)

    parsed_items.sort(key=lambda x: x["sort_key"])
    auto_suffix_applied_items = _apply_auto_suffix(parsed_items)

    for item in parsed_items:
        _finalize_item(item)

    parsed_items.sort(key=lambda x: x["sort_key"])
    unparsed_items.sort(key=lambda x: x["index"])

    output_items = parsed_items + unparsed_items
    formatted_text = "\n".join([item["text"] for item in output_items])

    failed_items = []
    for item in unparsed_items:
        reasons = [w for w in item["warnings"] if w in ("year_missing", "author_missing", "author_parse_failed")]
        failed_items.append({
            "text": item["text"],
            "reason": reasons[0] if reasons else "parse_failed",
        })

    authors_year_parsed_items = sum(
        1
        for item in parsed_items
        if item["fields"]["first_author_surname"] and item["fields"]["year"]
    )

    report_items = []
    for item in output_items:
        report_items.append({
            "text": item["text"],
            "key": item.get("key", ""),
            "fields": item["fields"],
            "warnings": item["warnings"],
        })

    report = {
        "total_items": len(raw_items),
        "parsed_items": len(parsed_items),
        "authors_year_parsed_items": authors_year_parsed_items,
        "auto_suffix_applied_items": auto_suffix_applied_items,
        "failed_items": failed_items,
        "items": report_items,
    }

    return formatted_text, report
