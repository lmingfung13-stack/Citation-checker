import io
import sys
from pathlib import Path

from docx import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.analysis_service import run_file_analysis_with_reference_override
from services.reference_service import build_citation_key, extract_citations, parse_citation


def _collect_citation_keys(text: str) -> set[str]:
    keys = set()
    for citation in extract_citations(text):
        parsed = parse_citation(citation)
        key = build_citation_key(parsed)
        if key:
            keys.add(key)
    return keys


def _build_docx_bytes(lines: list[str]) -> bytes:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _assert_equal(name: str, actual, expected):
    if actual == expected:
        print(f"[PASS] {name}")
        return True
    print(f"[FAIL] {name} | expected={expected} actual={actual}")
    return False


def _assert_true(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"[PASS] {name}")
        return True
    print(f"[FAIL] {name} | {detail}")
    return False


def run_key_behavior_checks() -> bool:
    ok = True

    text_and_amp = "DiMaggio and Powell (1983) and related work (DiMaggio & Powell, 1983)."
    keys_and_amp = _collect_citation_keys(text_and_amp)
    ok &= _assert_equal("and_vs_ampersand", keys_and_amp, {"dimaggio_1983"})

    text_multi = "Prior work (Baier et al., 2020; Chava, 2014) supports this model."
    keys_multi = _collect_citation_keys(text_multi)
    ok &= _assert_equal("multi_citation_semicolon", keys_multi, {"baier_2020", "chava_2014"})

    text_suffix = "Results differ for (Garcia, 2020a) and (Garcia, 2020b)."
    keys_suffix = _collect_citation_keys(text_suffix)
    ok &= _assert_equal("year_suffix_a_b", keys_suffix, {"garcia_2020a", "garcia_2020b"})

    return ok


def run_override_path_checks() -> bool:
    ok = True

    docx_bytes = _build_docx_bytes(
        [
            "This study builds on prior work (Baier et al., 2020; Chava, 2014).",
            "Garcia (2020a) extends the prior findings.",
            "References",
            "Baier, P., Berninger, M., & Kiesel, F. (2020). Environmental reporting in annual reports. Journal A.",
            "Garcia, L. (2020a). Sustainability assurance timing. Journal C.",
        ]
    )

    auto_results, auto_meta = run_file_analysis_with_reference_override(
        file_bytes=docx_bytes,
        filename="mock_single_path.docx",
        file_type="docx",
    )

    override_reference_text = "\n".join(
        [
            "Baier, P., Berninger, M., & Kiesel, F. (2020). Environmental reporting in annual reports. Journal A.",
            "Chava, S. (2014). Environmental externalities and cost of capital. Journal B.",
            "Garcia, L. (2020a). Sustainability assurance timing. Journal C.",
        ]
    )

    override_results, override_meta = run_file_analysis_with_reference_override(
        file_bytes=docx_bytes,
        filename="mock_single_path.docx",
        file_type="docx",
        override_reference_text=override_reference_text,
    )

    ok &= _assert_true(
        "single_result_shape_auto",
        isinstance(auto_results, tuple) and len(auto_results) == 4,
        detail=f"type={type(auto_results)} len={len(auto_results) if isinstance(auto_results, tuple) else 'n/a'}",
    )
    ok &= _assert_true(
        "single_result_shape_override",
        isinstance(override_results, tuple) and len(override_results) == 4,
        detail=f"type={type(override_results)} len={len(override_results) if isinstance(override_results, tuple) else 'n/a'}",
    )

    ok &= _assert_equal("source_auto", auto_meta.get("reference_source"), "auto_extracted")
    ok &= _assert_equal("source_override", override_meta.get("reference_source"), "user_override")

    auto_summary, auto_matched, auto_missing, auto_uncited = auto_results
    over_summary, over_matched, over_missing, over_uncited = override_results

    # Keep behavior deterministic: one formal result path in both modes (same four-table contract).
    ok &= _assert_true(
        "four_tables_auto",
        all(hasattr(df, "shape") for df in (auto_summary, auto_matched, auto_missing, auto_uncited)),
        detail="auto results are not all DataFrame-like",
    )
    ok &= _assert_true(
        "four_tables_override",
        all(hasattr(df, "shape") for df in (over_summary, over_matched, over_missing, over_uncited)),
        detail="override results are not all DataFrame-like",
    )

    ok &= _assert_true(
        "override_not_worse_missing",
        len(over_missing) <= len(auto_missing),
        detail=f"auto_missing={len(auto_missing)} override_missing={len(over_missing)}",
    )

    return ok


def main() -> int:
    checks_ok = True

    print("=== Citation key behavior checks ===")
    checks_ok &= run_key_behavior_checks()

    print("=== Single-path override checks ===")
    checks_ok &= run_override_path_checks()

    if checks_ok:
        print("---")
        print("ALL CHECKS PASS")
        return 0

    print("---")
    print("CHECKS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
