# Phase 4 reconciliation

Generated: `2026-09-05T20:34:35.256652+00:00`  
Status: **SUCCESS**

This report reconciles the immutable Silver snapshot currently registered in Athena. Newer Bronze runs are listed separately and are not treated as missing rows.

## Inspection flow

| Layer | Rows | Explanation |
|---|---:|---|
| Selected Bronze | 250,379 | Successful production runs selected by the Silver build |
| Silver | 247,714 | Removed 2,665 exact overlap duplicates; rejected 0 |
| Staging | 247,714 | Thin view; no rows removed |
| Inspection fact | 247,714 | Same inspection/violation grain as staging |
| Inspection events | 78,353 | Multiple violation rows collapsed only for inspection-level metrics |

## 311 complaint flow

| Layer | Rows | Explanation |
|---|---:|---|
| Selected Bronze | 151,170 | Successful production runs selected by the Silver build |
| Silver | 150,231 | Removed 939 repeated complaint IDs; rejected 0 |
| Staging | 150,231 | Thin view; no rows removed |
| Complaint fact | 150,231 | One row per complaint |

## Dimensions and marts

Dimensions and marts have different grains, so their counts should not equal fact counts.

| Dataset | Rows | Grain |
|---|---:|---|
| `dim_restaurant` | 27,220 | One row per CAMIS |
| `dim_chain` | 705 | One row per normalized name with 3+ locations |
| `dim_borough` | 5 | One row per NYC borough |
| `dim_date` | 1,097 | One row per calendar day |
| `dim_violation` | 113 | One row per violation code |
| `dim_complaint_type` | 3 | One row per complaint type |
| `mart_borough_grade_summary` | 18 | Six areas × three grades |
| `mart_cuisine_borough_heatmap` | 362 | One row per cuisine and borough |
| `mart_violation_by_borough` | 477 | One row per violation and borough |
| `mart_weekly_311_vs_inspection` | 942 | One row per week and area |
| `mart_restaurant_grade_history` | 42,826 | One row per graded inspection |
| `mart_chain_summary` | 705 | One row per chain |

## Newer Bronze rows awaiting Silver

- DOHMH inspections: **3,441** rows across 1 run(s).
- 311 complaints: **1,108** rows across 1 run(s).

These rows arrived after the current Phase 3 snapshot. They will enter Silver and Gold when the transformation pipeline is rerun; they are not unexplained loss.

## Validation

All **19** reconciliation checks passed. The separate dbt suite also passed all 119 data tests.
