"""Unit tests for Phase 7 Athena, risk, caching, and validation behavior."""

import io
import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from api.config import Settings
from api.services.athena import AthenaQueryService, AthenaQueryTimeout
from api.services.overview import OverviewService
from api.services.presentation import REPEATED_CRITICAL_CTES
from api.services.risk import RiskScoreError, RiskScoreService
from api.services.sql import normalized_borough, sql_string, validated_key


def settings() -> Settings:
    return Settings(
        safeeats_s3_bucket="test-bucket",
        aws_profile=None,
        api_cache_ttl_seconds=300,
    )


def test_athena_reads_paginated_typed_results_and_caches() -> None:
    client = Mock()
    client.start_query_execution.return_value = {"QueryExecutionId": "query-1"}
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
    }
    metadata = {
        "ColumnInfo": [
            {"Name": "count", "Type": "bigint"},
            {"Name": "rate", "Type": "double"},
            {"Name": "current", "Type": "boolean"},
        ]
    }
    client.get_query_results.side_effect = [
        {
            "ResultSet": {
                "ResultSetMetadata": metadata,
                "Rows": [
                    {"Data": [{"VarCharValue": "count"}]},
                    {
                        "Data": [
                            {"VarCharValue": "2"},
                            {"VarCharValue": "1.5"},
                            {"VarCharValue": "true"},
                        ]
                    },
                ],
            },
            "NextToken": "next",
        },
        {
            "ResultSet": {
                "ResultSetMetadata": metadata,
                "Rows": [
                    {
                        "Data": [
                            {"VarCharValue": "3"},
                            {"VarCharValue": "2.5"},
                            {"VarCharValue": "false"},
                        ]
                    }
                ],
            }
        },
    ]
    service = AthenaQueryService(client, settings())

    first = service.query("select values", cache_key="values")
    second = service.query("select values", cache_key="values")

    assert first == [
        {"count": 2, "rate": 1.5, "current": True},
        {"count": 3, "rate": 2.5, "current": False},
    ]
    assert second == first
    assert client.start_query_execution.call_count == 1


def test_athena_timeout_stops_query() -> None:
    client = Mock()
    client.start_query_execution.return_value = {"QueryExecutionId": "query-2"}
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "RUNNING"}}
    }
    service = AthenaQueryService(client, settings())

    with pytest.raises(AthenaQueryTimeout):
        service.query("select slow", timeout_seconds=0.001)

    client.stop_query_execution.assert_called_once_with(QueryExecutionId="query-2")


def test_risk_score_normalization_and_malformed_factors() -> None:
    valid = RiskScoreService._normalize(
        {
            "restaurant_key": "a" * 64,
            "risk_probability": 0.18,
            "risk_category": "high",
            "main_contributing_factors": '[{"feature":"score","contribution":0.2}]',
            "model_version": "model-v1",
            "scoring_timestamp": "2026-09-06T00:00:00+00:00",
        }
    )
    assert valid["risk_category"] == "HIGH"
    assert valid["main_contributing_factors"][0]["feature"] == "score"

    invalid = {**valid, "main_contributing_factors": "not-json"}
    with pytest.raises(RiskScoreError, match="malformed"):
        RiskScoreService._normalize(invalid)


def test_risk_summary_uses_small_manifest_and_cache() -> None:
    client = Mock()
    pointer = {
        "score_run_id": "scores-v1",
        "score_key": "ml/current_scores/run_id=scores-v1/scores.parquet",
        "scoring_report_key": "ml/current_scores/run_id=scores-v1/scoring_report.json",
    }
    report = {
        "score_run_id": "scores-v1",
        "model_version": "model-v1",
        "scoring_timestamp": "2026-09-06T00:00:00+00:00",
    }
    client.get_object.side_effect = [
        {"Body": io.BytesIO(json.dumps(pointer).encode("utf-8"))},
        {"Body": io.BytesIO(json.dumps(report).encode("utf-8"))},
    ]
    service = RiskScoreService(client, settings())

    assert service.summary() == report
    assert service.summary() == report
    assert client.get_object.call_count == 2


def test_repeated_critical_rule_uses_distinct_inspections() -> None:
    normalized = " ".join(REPEATED_CRITICAL_CTES.lower().split())
    assert "count(distinct facts.inspection_id)" in normalized
    assert "having count(distinct facts.inspection_id) >= 2" in normalized
    assert "dates.calendar_date >= date_add('year', -3, current_date)" in normalized


def test_kpi_trends_are_honest_and_do_not_show_negative_zero() -> None:
    assert OverviewService.kpi_trend("active_restaurants", 100, None) == {
        "trend": "Current snapshot",
        "trend_tone": "neutral",
    }
    assert OverviewService.kpi_trend("average_inspection_score", 11.396, 11.415) == {
        "trend": "0.0pt MoM",
        "trend_tone": "neutral",
    }
    assert OverviewService.kpi_trend("temporary_closures_ytd", 525, 7) == {
        "trend": "+7 this month",
        "trend_tone": "negative",
    }


def test_sql_validation_accepts_display_case_and_escapes_text() -> None:
    assert normalized_borough("Staten Island") == "STATEN ISLAND"
    assert sql_string("Joe's") == "'Joe''s'"
    assert validated_key("a" * 64, "Restaurant key") == "a" * 64

    with pytest.raises(HTTPException) as borough_error:
        normalized_borough("Albany")
    assert borough_error.value.status_code == 422

    with pytest.raises(HTTPException) as key_error:
        validated_key("unsafe'key", "Restaurant key")
    assert key_error.value.status_code == 422
