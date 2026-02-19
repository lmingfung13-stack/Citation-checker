# Tool2 Matching Layered Test Report

- Generated at (ISO): 2026-02-18T19:48:21+08:00
- Dataset version: 2

## Summary

- total: 5
- passed: 1
- failed: 1
- skipped: 3
- level1_pass_count: 1
- level1_fail_count: 1
- level1_avg_f1: 0.8333
- level1_count_asserted_count: 2
- level1_count_pass_count: 1
- level1_count_fail_count: 1
- level1_count_avg_f1: 0.8333
- level2_auto_pass_count: 2
- level2_auto_fail_count: 0
- level2_auto_not_asserted_count: 0
- level2_auto_avg_f1: 1.0000
- level2_manual_pass_count: 0
- level2_manual_fail_count: 0
- level2_manual_not_asserted_count: 2
- level2_manual_avg_f1: n/a
- level3_info_count: 5

## Per-Case Layer Status

- t001 single_doc_case | overall=failed | L1=failed (e=3, a=3, sim=0.6667, count=failed:0.6667) | L2-auto=passed (e=3, a=3, sim=1.0000) | L2-manual=not_asserted (e=0, a=0, sim=1.0000)
- t002 esg_doc_case | overall=passed | L1=passed (e=16, a=16, sim=1.0000, count=passed:1.0000) | L2-auto=passed (e=33, a=33, sim=1.0000) | L2-manual=not_asserted (e=0, a=0, sim=1.0000)
- t003 greenwash_board_moderation_pdf_case: skipped (missing_expected_level1)
- t004 low_effects_industry_specialization_2004: skipped (missing_expected_level1)
- t005 bank_loan_cost_pdf_case: skipped (missing_expected_level1)

## Failures

### t001 single_doc_case

- file: generated_case_01.docx
- reason: layer_assertion_failed:level1
- used_mode: before_heading
- used_fallback: False
- reference_heading_found: True
- text_preview: This study follows Baier et al. (2020) and Chava (2014). We also discuss disclosure behavior (Barnea & Rubin, 2010). Additional context is provided for investor...
- citation_raw_preview: Barnea & Rubin, 2010 | This study follows Baier et al. (2020) | and Chava (2014)
- reference_raw_preview: References | Baier, P., Berninger, M., & Kiesel, F. (2020). Environmental, social and governance reporting in annual reports: A textual analysis. Financial Markets, Institutions & Instruments, 29(3), 93-118. | Chava, S. (2014). Environmental externalities and cost of capital. Management Science, 60(9), 2223-2247. | Barnea, A., & Rubin, A. (2010). Corporate social responsibility as a conflict betwe...
- level1_metrics:
  - status: failed
  - count(expected/actual/overlap): 3/3/2
  - similarity(precision/recall/f1/jaccard): 0.6667/0.6667/0.6667/0.5000
  - count_asserted: True
  - count_status: failed
  - count(expected/actual/overlap): 3/3/2
  - count_similarity(precision/recall/f1): 0.6667/0.6667/0.6667
- level2_auto_metrics:
  - status: passed
  - count(expected/actual/overlap): 3/3/3
  - similarity(precision/recall/f1/jaccard): 1.0000/1.0000/1.0000/1.0000
- level2_manual_metrics:
  - status: not_asserted
  - count(expected/actual/overlap): 0/0/0
  - similarity(precision/recall/f1/jaccard): 1.0000/1.0000/1.0000/1.0000
- level1:
```json
{
  "asserted": true,
  "passed": false,
  "status": "failed",
  "expected_keys": [
    "baier_2020",
    "barnea_2010",
    "chava_2014"
  ],
  "actual_keys": [
    "barnea_2010",
    "chava_2014",
    "thisstudyfollowsbaier_2020"
  ],
  "expected_key_counts": {
    "baier_2020": 1,
    "barnea_2010": 1,
    "chava_2014": 1
  },
  "actual_key_counts": {
    "barnea_2010": 1,
    "chava_2014": 1,
    "thisstudyfollowsbaier_2020": 1
  },
  "count_asserted": true,
  "count_passed": false,
  "count_status": "failed",
  "count_expected_total": 3,
  "count_actual_total": 3,
  "count_overlap_total": 2,
  "count_precision": 0.6666666666666666,
  "count_recall": 0.6666666666666666,
  "count_f1": 0.6666666666666666,
  "count_mismatch_keys": {
    "baier_2020": {
      "expected": 1,
      "actual": 0,
      "delta": -1
    },
    "thisstudyfollowsbaier_2020": {
      "expected": 0,
      "actual": 1,
      "delta": 1
    }
  },
  "expected_count": 3,
  "actual_count": 3,
  "overlap_count": 2,
  "missing_keys": [
    "baier_2020"
  ],
  "extra_keys": [
    "thisstudyfollowsbaier_2020"
  ],
  "precision": 0.6666666666666666,
  "recall": 0.6666666666666666,
  "f1": 0.6666666666666666,
  "jaccard": 0.5
}
```
- level2_auto:
```json
{
  "asserted": true,
  "passed": true,
  "status": "passed",
  "expected_keys": [
    "baier_2020",
    "barnea_2010",
    "chava_2014"
  ],
  "actual_keys": [
    "baier_2020",
    "barnea_2010",
    "chava_2014"
  ],
  "expected_count": 3,
  "actual_count": 3,
  "overlap_count": 3,
  "missing_keys": [],
  "extra_keys": [],
  "precision": 1.0,
  "recall": 1.0,
  "f1": 1.0,
  "jaccard": 1.0,
  "position": {
    "asserted": true,
    "status": "passed",
    "passed": true,
    "mode": "strict_pasted_items",
    "expected_count": 3,
    "actual_count": 3,
    "matched_count": 3,
    "missing_keys": [],
    "mismatch_keys": [],
    "extra_keys": [],
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0,
    "strict_exact_ratio": 1.0
  },
  "parsed_fields": {
    "asserted": true,
    "status": "passed",
    "passed": true,
    "expected_items": 3,
    "matched_items": 3,
    "expected_fields": 17,
    "matched_fields": 17,
    "field_accuracy": 1.0,
    "failed_keys": []
  },
  "parse_coverage": {
    "total_items": 3,
    "source_detected_count": 3,
    "source_detected_ratio": 1.0,
    "title_detected_count": 3,
    "journal_detected_count": 3,
    "title_detected_ratio": 1.0,
    "journal_detected_ratio": 1.0
  },
  "duplicate_keys": [],
  "key_status": "passed"
}
```
- level2_manual:
```json
{
  "asserted": false,
  "passed": true,
  "status": "not_asserted",
  "expected_keys": [],
  "actual_keys": [],
  "expected_count": 0,
  "actual_count": 0,
  "manual_parse_failed_count": 0,
  "overlap_count": 0,
  "missing_keys": [],
  "extra_keys": [],
  "precision": 1.0,
  "recall": 1.0,
  "f1": 1.0,
  "jaccard": 1.0,
  "position": {
    "asserted": false,
    "status": "not_asserted",
    "passed": true,
    "expected_count": 0,
    "actual_count": 0,
    "matched_count": 0,
    "missing_keys": [],
    "mismatch_keys": [],
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0
  },
  "parsed_fields": {
    "asserted": false,
    "status": "not_asserted",
    "passed": true,
    "expected_items": 0,
    "matched_items": 0,
    "expected_fields": 0,
    "matched_fields": 0,
    "field_accuracy": 1.0,
    "failed_keys": []
  },
  "parse_coverage": {
    "total_items": 0,
    "source_detected_count": 0,
    "source_detected_ratio": 0.0,
    "title_detected_count": 0,
    "journal_detected_count": 0,
    "title_detected_ratio": 0.0,
    "journal_detected_ratio": 0.0
  },
  "duplicate_keys": [],
  "key_status": "not_asserted"
}
```
- level3_info:
```json
{
  "matched_count": 2,
  "missing_count": 1,
  "uncited_count": 1
}
```

## Not Asserted

- t001 single_doc_case: not_asserted=level2_manual
- t002 esg_doc_case: not_asserted=level2_manual

## Level3 Informational

- t001 single_doc_case: matched=2, missing=1, uncited=1
- t002 esg_doc_case: matched=16, missing=1, uncited=22

