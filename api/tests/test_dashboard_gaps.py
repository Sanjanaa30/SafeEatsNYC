"""Tests for Phase 7 dashboard-specific presentation calculations."""

from api.routers.chains import chain_risk_rollups
from api.services.correlation import describe_correlation
from api.services.metadata import MetadataService
from api.services.overview import OverviewService
from api.services.restaurants import RestaurantService


class FakeRiskService:
    def by_restaurant_key(self) -> dict:
        return {
            "restaurant-a": {
                "risk_probability": 0.2,
                "risk_category": "LOW",
            },
            "restaurant-b": {
                "risk_probability": 0.8,
                "risk_category": "HIGH",
            },
        }


def test_chain_risk_rollup_uses_location_scores_and_repeat_flags() -> None:
    locations = [
        {
            "chain_key": "chain-a",
            "restaurant_key": "restaurant-a",
            "restaurant_name": "Location A",
            "has_repeated_critical_violation": False,
        },
        {
            "chain_key": "chain-a",
            "restaurant_key": "restaurant-b",
            "restaurant_name": "Location B",
            "has_repeated_critical_violation": True,
        },
    ]

    result = chain_risk_rollups(FakeRiskService(), locations)["chain-a"]

    assert result["average_risk_probability"] == 0.5
    assert result["high_risk_location_count"] == 1
    assert result["highest_risk_location"]["restaurant_key"] == "restaurant-b"
    assert result["has_repeated_critical_location"] is True


class CapturingAthena:
    def __init__(self, responses: list[list[dict]]) -> None:
        self.responses = responses
        self.queries: list[str] = []

    def query(self, sql: str, **_: object) -> list[dict]:
        self.queries.append(sql)
        return self.responses.pop(0)


def test_correlation_uses_three_clear_strength_bands() -> None:
    assert describe_correlation("NYC", 26, 2, 26, 0.29)["strength"] == "weak"
    assert describe_correlation("NYC", 26, 2, 26, 0.30)["strength"] == "moderate"
    assert describe_correlation("NYC", 26, 2, 26, -0.59)["strength"] == "moderate"
    assert describe_correlation("NYC", 26, 2, 26, -0.60)["strength"] == "strong"


def test_current_restaurant_summary_starts_with_all_current_restaurants() -> None:
    athena = CapturingAthena([[{"restaurant_key": "key"}], [{"total": 1}]])
    service = RestaurantService(athena)

    service.search(
        query=None,
        borough="Queens",
        cuisine=None,
        grade=None,
        flag=None,
        sort="name",
        direction="asc",
        page=1,
        page_size=20,
    )

    normalized = " ".join(athena.queries[0].lower().split())
    assert "from dim_restaurant r" in normalized
    assert "left join mart_restaurant_grade_history h" in normalized
    assert "has_repeated_critical_violation" in normalized


def test_restaurant_search_matches_name_id_address_zip_and_borough_terms() -> None:
    athena = CapturingAthena([[{"restaurant_key": "key"}], [{"total": 1}]])
    service = RestaurantService(athena)

    service.search(
        query="Tony's Brick Oven in Staten Island Bay Street",
        borough=None,
        cuisine=None,
        grade=None,
        flag=None,
        sort="name",
        direction="asc",
        page=1,
        page_size=20,
    )

    normalized = " ".join(athena.queries[0].lower().split())
    assert "r.restaurant_name_normalized" in normalized
    assert "r.camis" in normalized
    assert "r.address" in normalized
    assert "r.zipcode" in normalized
    assert "b.borough_name" in normalized
    assert "like '%tony%'" in normalized
    assert "like '%brick%'" in normalized
    assert "like '%bay%'" in normalized
    assert "not r.is_chain" not in normalized


def test_citywide_kpis_have_six_explicit_definitions() -> None:
    metrics = [
        "active_restaurants",
        "grade_a_compliance_rate",
        "average_inspection_score",
        "critical_violation_rate",
        "open_311_food_complaints",
        "temporary_closures_ytd",
    ]
    athena = CapturingAthena(
        [[{"metric": metric, "value": 1.0, "comparison": 1.0} for metric in metrics]]
    )

    rows = OverviewService(athena).kpis()

    assert len(rows) == 6
    assert all(row["definition"] and row["period"] and row["unit"] for row in rows)
    assert all(row["trend"] and row["trend_tone"] for row in rows)
    assert "inspection_action" in " ".join(athena.queries[0].lower().split())


def test_borough_cards_use_live_issue_complaint_and_improvement_metrics() -> None:
    athena = CapturingAthena(
        [
            [
                {
                    "borough_name": "BROOKLYN",
                    "grade_a_percent": 90.0,
                    "complaint_rate_per_1000": 12.5,
                    "improvement_rate": 8.0,
                }
            ]
        ]
    )

    rows = OverviewService(athena).boroughs("complaint_rate")

    assert rows[0]["safety_rank"] == 1
    query = " ".join(athena.queries[0].lower().split())
    assert "mart_violation_by_borough" in query
    assert "complaint_rate_per_1000 asc" in query
    assert "improvement_rate" in query


def test_overview_chart_queries_use_gold_marts_and_latest_grade_percentages() -> None:
    athena = CapturingAthena([[{}], [{}]])
    service = OverviewService(athena)

    service.grade_distribution_by_borough()
    service.cuisine_heatmap()

    grade_query, heatmap_query = (
        " ".join(query.lower().split()) for query in athena.queries
    )
    assert "mart_borough_grade_summary" in grade_query
    assert "case when grade = 'a'" in grade_query
    assert "familiar_cuisines" in heatmap_query
    assert "('american', 'american')" in heatmap_query
    assert "latest.grade in ('b', 'c')" in heatmap_query


def test_violation_criticality_chart_uses_distinct_inspections_as_denominator() -> None:
    athena = CapturingAthena([[{}]])

    OverviewService(athena).violation_criticality_by_borough()

    query = " ".join(athena.queries[0].lower().split())
    assert "from mart_violation_by_borough" in query
    assert "from fact_inspection as facts" in query
    assert "count(distinct facts.inspection_id)" in query
    assert "group by borough_name" in query
    assert "when is_critical then violation_count" in query
    assert "when not is_critical then violation_count" in query
    assert query.count("nullif(inspections.inspection_count, 0)") == 2


def test_violation_labels_shorten_common_wording_without_losing_official_text() -> None:
    description = "Non-food contact surface or equipment made of unacceptable material, not kept clean."
    athena = CapturingAthena(
        [[{"violation_description": description, "violation_count": 5}]]
    )

    rows = OverviewService(athena).violations(None, "all", "frequency", 5)

    assert rows[0]["short_label"] == "Equipment or surfaces hard to clean"
    assert rows[0]["violation_description"] == description


def test_freshness_includes_inspection_coverage_start_date() -> None:
    athena = CapturingAthena(
        [
            [
                {
                    "earliest_inspection_date": "2023-08-30",
                    "latest_inspection_date": "2026-09-02",
                    "latest_complaint_date": "2026-09-05",
                }
            ]
        ]
    )

    result = MetadataService(athena, None, None).freshness(
        {"score_run_id": "test", "scoring_timestamp": "2026-09-06"}
    )

    assert result["earliest_inspection_date"] == "2023-08-30"
    assert "min(calendar_date)" in athena.queries[0].lower()
