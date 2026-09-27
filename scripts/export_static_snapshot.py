"""Export the live dashboard data for the free, API-free Vercel build."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "public" / "data" / "snapshot"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.dependencies import (  # noqa: E402
    get_athena_service,
    get_chain_service,
    get_correlation_service,
    get_metadata_service,
    get_overview_service,
    get_restaurant_service,
)
from api.services.presentation import (  # noqa: E402
    REPEATED_CRITICAL_COLUMNS,
    REPEATED_CRITICAL_CTES,
)


def write_json(path: Path, value: Any) -> None:
    """Write compact UTF-8 JSON so the browser downloads less data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def chunk_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict]]:
    """Group restaurant records by the first hexadecimal key character."""

    chunks: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        chunk = str(row[key]).lower()[:1] or "other"
        chunks[chunk].append(row)
    return dict(chunks)


def export_restaurants() -> list[dict[str, Any]]:
    """Read every current restaurant in one Athena query."""

    athena = get_athena_service()
    return athena.query(
        f"""
        with {REPEATED_CRITICAL_CTES},
        latest_grade_by_year as (
            select restaurant_key, year(inspection_date) as grade_year,
                   max_by(grade, inspection_date) as grade
            from mart_restaurant_grade_history
            where inspection_date >= date_add(
                'year', -2, date_trunc('year', current_date)
            )
            group by restaurant_key, year(inspection_date)
        ),
        three_year_grade_trend as (
            select restaurant_key,
                   array_agg(grade order by grade_year) as three_year_grades
            from latest_grade_by_year
            group by restaurant_key
        )
        select r.restaurant_key, r.camis as restaurant_id, r.restaurant_name,
               r.restaurant_name_normalized, r.address, r.zipcode, r.nta_name,
               b.borough_name, r.cuisine, r.latitude, r.longitude,
               h.grade as current_grade, h.score as current_score,
               h.inspection_date as latest_inspection_date,
               h.days_since_inspection, h.is_grade_consistent, h.improved_to_a,
               r.is_chain, r.is_confirmed_fast_food, r.chain_key,
               coalesce(
                   trend.three_year_grades,
                   cast(array[] as array(varchar))
               ) as three_year_grades,
               {REPEATED_CRITICAL_COLUMNS}
        from dim_restaurant r
        left join dim_borough b on r.borough_key = b.borough_key
        left join mart_restaurant_grade_history h
          on r.restaurant_key = h.restaurant_key
         and h.inspection_recency_rank = 1
        left join three_year_grade_trend trend
          on r.restaurant_key = trend.restaurant_key
        left join repeated_critical_summary repeats
          on r.restaurant_key = repeats.restaurant_key
        order by r.restaurant_name, r.restaurant_key
        """
    )


def export_history() -> list[dict[str, Any]]:
    """Read the inspection history needed by restaurant modals."""

    return get_athena_service().query(
        """
        select restaurant_key, inspection_id, inspection_date, grade,
               previous_grade, score, violation_count,
               critical_violation_count, has_critical_violation, improved_to_a
        from mart_restaurant_grade_history
        order by restaurant_key, inspection_date desc, inspection_id desc
        """
    )


def export_violations() -> list[dict[str, Any]]:
    """Read the six distinct recent finding types shown in each modal."""

    return get_athena_service().query(
        """
        with unique_findings as (
            select f.restaurant_key, f.inspection_id,
                   d.calendar_date as inspection_date,
                   v.violation_code, v.violation_description, v.is_critical,
                   row_number() over (
                       partition by f.restaurant_key, v.violation_description
                       order by d.calendar_date desc, v.is_critical desc,
                                v.violation_code
                   ) as type_rank
            from fact_inspection f
            join dim_date d on f.date_key = d.date_key
            join dim_violation v on f.violation_key = v.violation_key
        ), ranked as (
            select *, row_number() over (
                       partition by f.restaurant_key
                       order by f.inspection_date desc, f.is_critical desc,
                                f.violation_code
                   ) as finding_rank
            from unique_findings f
            where type_rank = 1
        )
        select restaurant_key, inspection_id, inspection_date, violation_code,
               violation_description, is_critical
        from ranked
        where finding_rank <= 6
        order by restaurant_key, inspection_date desc, is_critical desc,
                 violation_code
        """,
        timeout_seconds=300,
    )


def load_risk_scores() -> list[dict[str, Any]]:
    """Load scores from S3, or use the running local API without PyArrow."""

    try:
        from api.dependencies import get_risk_score_service

        return get_risk_score_service().load()
    except ModuleNotFoundError as error:
        if error.name != "pyarrow":
            raise

    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urlencode({"page": page, "page_size": 100})
        with urlopen(
            f"http://localhost:8000/api/v1/risk/restaurants?{query}",
            timeout=120,
        ) as response:
            payload = json.load(response)
        rows.extend(payload["items"])
        if len(rows) >= int(payload["total"]):
            return rows
        page += 1


def add_chain_rollups(
    chains: list[dict[str, Any]],
    restaurants: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> None:
    """Add location-level prediction summaries to each chain."""

    score_by_key = {row["restaurant_key"]: row for row in scores}
    locations_by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for restaurant in restaurants:
        if restaurant.get("chain_key"):
            locations_by_chain[restaurant["chain_key"]].append(restaurant)

    for chain in chains:
        locations = locations_by_chain.get(chain["chain_key"], [])
        scored = [
            (location, score_by_key[location["restaurant_key"]])
            for location in locations
            if location["restaurant_key"] in score_by_key
        ]
        probabilities = [score["risk_probability"] for _, score in scored]
        highest = max(
            scored,
            key=lambda item: item[1]["risk_probability"],
            default=None,
        )
        chain.update(
            {
                "average_risk_probability": (
                    sum(probabilities) / len(probabilities)
                    if probabilities
                    else None
                ),
                "high_risk_location_count": sum(
                    score["risk_category"] == "HIGH" for _, score in scored
                ),
                "highest_risk_location": (
                    {
                        "restaurant_key": highest[0]["restaurant_key"],
                        "restaurant_name": highest[0].get("restaurant_name"),
                        "risk_probability": highest[1]["risk_probability"],
                        "risk_category": highest[1]["risk_category"],
                    }
                    if highest
                    else None
                ),
                "has_repeated_critical_location": any(
                    location.get("has_repeated_critical_violation", False)
                    for location in locations
                ),
            }
        )


def main() -> None:
    """Build all files consumed by the browser snapshot adapter."""

    metadata_service = get_metadata_service()
    overview = get_overview_service()
    correlation = get_correlation_service()
    restaurant_service = get_restaurant_service()
    chain_service = get_chain_service()

    metadata = metadata_service.metadata()
    freshness = metadata_service.freshness()
    restaurants = export_restaurants()
    scores = load_risk_scores()
    score_by_key = {row["restaurant_key"]: row for row in scores}

    for restaurant in restaurants:
        score = score_by_key.get(restaurant["restaurant_key"])
        restaurant["risk_probability"] = (
            score.get("risk_probability") if score else None
        )
        restaurant["risk_category"] = score.get("risk_category") if score else None

    risk_rows = []
    restaurant_by_key = {row["restaurant_key"]: row for row in restaurants}
    for score in scores:
        restaurant = restaurant_by_key.get(score["restaurant_key"], {})
        risk_rows.append({**score, **restaurant})

    grade_trends = restaurant_service.grade_trends()

    chains, _ = chain_service.search(
        query=None, borough=None, confirmed_fast_food_only=False
    )
    add_chain_rollups(chains, restaurants, scores)

    recently_improved = restaurant_service.recently_improved(50)
    for restaurant in recently_improved:
        score = score_by_key.get(restaurant["restaurant_key"])
        restaurant["risk_probability"] = (
            score.get("risk_probability") if score else None
        )
        restaurant["risk_category"] = score.get("risk_category") if score else None

    overview_data = {
        "kpis": overview.kpis(),
        "boroughs": overview.boroughs("safety_rank"),
        "grade_distribution": overview.grade_distribution_by_borough(),
        "cuisine_heatmap": overview.cuisine_heatmap(),
        "violations": {
            criticality: overview.violations(
                None, criticality, "frequency", 100
            )
            for criticality in ["all", "critical", "non_critical"]
        },
        "violation_criticality_by_borough": (
            overview.violation_criticality_by_borough()
        ),
    }

    weekly = {
        complaint_type: correlation._weekly_rows("1 = 1", 104, complaint_type)
        for complaint_type in ["ALL", "FOOD_ESTABLISHMENT", "FOOD_POISONING", "RODENT"]
    }
    correlation_data = {
        "weekly": weekly,
        "restaurant_level": correlation.restaurant_level(28),
    }

    write_json(OUTPUT_DIR / "metadata.json", {"metadata": metadata, "freshness": freshness})
    write_json(OUTPUT_DIR / "overview.json", overview_data)
    write_json(OUTPUT_DIR / "correlation.json", correlation_data)
    write_json(OUTPUT_DIR / "restaurants.json", restaurants)
    write_json(OUTPUT_DIR / "chains.json", chains)
    write_json(OUTPUT_DIR / "risk.json", risk_rows)
    write_json(OUTPUT_DIR / "risk-grade-trends.json", grade_trends)
    write_json(OUTPUT_DIR / "recently-improved.json", recently_improved)

    history_chunks = chunk_by_key(export_history(), "restaurant_key")
    violation_chunks = chunk_by_key(export_violations(), "restaurant_key")
    for name, chunks in [
        ("history", history_chunks),
        ("violations", violation_chunks),
    ]:
        for chunk, values in chunks.items():
            write_json(OUTPUT_DIR / name / f"{chunk}.json", values)

    manifest = {
        "snapshot_date": freshness.get("latest_inspection_date"),
        "restaurant_count": len(restaurants),
        "chain_count": len(chains),
        "risk_score_count": len(risk_rows),
        "history_chunks": sorted(history_chunks),
        "violation_chunks": sorted(violation_chunks),
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
