"""Small tests for deterministic Phase 6 run naming."""

from datetime import datetime, timezone

import pytest

from orchestration.run_context import run_names, safe_run_token


def test_airflow_run_id_becomes_s3_safe_and_deterministic():
    value = "scheduled__2026-09-06T10:00:00-04:00"
    assert safe_run_token(value) == "scheduled__2026-09-06T10_00_00-04_00"
    assert safe_run_token(value) == safe_run_token(value)


def test_empty_run_id_is_rejected():
    with pytest.raises(ValueError):
        safe_run_token(":::")


def test_all_stage_names_share_one_run_token():
    names = run_names(
        "manual__phase6-check",
        datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc),
    )
    assert names == {
        "pipeline_run_id": "manual__phase6-check",
        "run_token": "manual__phase6-check",
        "inspections_silver_run_id": "inspections-silver-manual__phase6-check",
        "complaints_silver_run_id": "complaints-silver-manual__phase6-check",
        "matches_run_id": "complaint-restaurant-matches-manual__phase6-check",
        "scoring_date": "2026-09-06",
    }
