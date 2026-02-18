from __future__ import annotations

import json
from pathlib import Path


def load_stroke_map(path: str = "data/stroke_map.json") -> dict[str, int]:
    stroke_path = Path(path)
    with stroke_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    stroke_map: dict[str, int] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        try:
            stroke_map[k] = int(v)
        except (TypeError, ValueError):
            continue
    return stroke_map


def _find_first_cjk_unified_char(text: str) -> str:
    for ch in text or "":
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF:
            return ch
    return ""


def chinese_stroke_sort_key(reference_item_text: str, stroke_map: dict[str, int]) -> tuple:
    key_char = _find_first_cjk_unified_char(reference_item_text or "")
    strokes = stroke_map.get(key_char, 9999) if key_char else 9999
    return (strokes, key_char, reference_item_text)

