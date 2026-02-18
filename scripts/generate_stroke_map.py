from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

UNIHAN_ZIP_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
DATA_DIR = Path("data")
UNIHAN_DIR = DATA_DIR / "unihan"
UNIHAN_ZIP_PATH = UNIHAN_DIR / "Unihan.zip"
UNIHAN_EXTRACT_DIR = UNIHAN_DIR / "extracted"
OUTPUT_PATH = DATA_DIR / "stroke_map.json"

CODEPOINT_PATTERN = re.compile(r"^U\+([0-9A-Fa-f]+)$")


def _ensure_unihan_zip() -> None:
    UNIHAN_DIR.mkdir(parents=True, exist_ok=True)
    if UNIHAN_ZIP_PATH.exists():
        print(f"[skip] Unihan zip already exists: {UNIHAN_ZIP_PATH}")
        return
    print(f"[download] {UNIHAN_ZIP_URL}")
    urlretrieve(UNIHAN_ZIP_URL, UNIHAN_ZIP_PATH)
    print(f"[ok] downloaded: {UNIHAN_ZIP_PATH}")


def _extract_unihan_zip() -> None:
    if UNIHAN_EXTRACT_DIR.exists():
        shutil.rmtree(UNIHAN_EXTRACT_DIR)
    UNIHAN_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(UNIHAN_ZIP_PATH, "r") as zf:
        zf.extractall(UNIHAN_EXTRACT_DIR)
    print(f"[ok] extracted to: {UNIHAN_EXTRACT_DIR}")


def _first_int_token(value: str) -> int | None:
    for token in value.strip().split():
        try:
            return int(token)
        except ValueError:
            continue
    return None


def _parse_stroke_map_from_unihan_files() -> dict[str, int]:
    stroke_map: dict[str, int] = {}
    txt_files = sorted(UNIHAN_EXTRACT_DIR.glob("Unihan_*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No Unihan_*.txt files found under {UNIHAN_EXTRACT_DIR}")

    # NOTE:
    # Do not assume kTotalStrokes is always in a specific Unihan_*.txt file.
    # Unicode releases may reorganize property placement across different files,
    # so we scan all Unihan_*.txt files for robustness.
    for txt_path in txt_files:
        with txt_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) < 3:
                    continue

                codepoint, prop, value = parts[0], parts[1], parts[2]
                if prop != "kTotalStrokes":
                    continue

                m = CODEPOINT_PATTERN.match(codepoint)
                if not m:
                    continue

                strokes = _first_int_token(value)
                if strokes is None:
                    continue

                char = chr(int(m.group(1), 16))
                stroke_map[char] = strokes

    return stroke_map


def _write_stroke_map(stroke_map: dict[str, int]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(stroke_map, f, ensure_ascii=False, sort_keys=True)
    print(f"[ok] wrote stroke map: {OUTPUT_PATH}")
    print(f"[summary] entries={len(stroke_map)}")


def _print_small_self_test(stroke_map: dict[str, int]) -> None:
    print("[self-test] lookup common chars")
    for ch in ("張", "陳", "李"):
        strokes = stroke_map.get(ch)
        if isinstance(strokes, int):
            print(f"  {ch}: {strokes}")
        else:
            print(f"  {ch}: <missing> (please update Unihan data or verify char coverage)")


def main() -> None:
    _ensure_unihan_zip()
    _extract_unihan_zip()
    stroke_map = _parse_stroke_map_from_unihan_files()
    _write_stroke_map(stroke_map)
    _print_small_self_test(stroke_map)


if __name__ == "__main__":
    main()

