"""Normalized weekly and restaurant-level complaint/inspection relationships."""

import math
from collections import defaultdict
from typing import Any

from api.services.athena import AthenaQueryService
from api.services.sql import normalized_borough, sql_string

COMPLAINT_TYPES = {"FOOD ESTABLISHMENT", "FOOD POISONING", "RODENT"}


def normalized_complaint_type(value: str | None) -> str | None:
    if not value or value.upper() == "ALL":
        return None
    normalized = value.replace("_", " ").strip().upper()
    return normalized if normalized in COMPLAINT_TYPES else None


class CorrelationService:
    def __init__(self, athena: AthenaQueryService) -> None:
        self.athena = athena

    def _weekly_rows(
        self, area_condition: str, weeks: int, complaint_type: str | None
    ) -> list[dict[str, Any]]:
        complaint_type = normalized_complaint_type(complaint_type)
        complaint_filter = (
            f"and upper(types.complaint_type) = {sql_string(complaint_type)}"
            if complaint_type
            else ""
        )
        return self.athena.query(
            f"""
            with recent_areas as (
                select *, row_number() over (
                    partition by borough_key order by week_start_date desc
                ) as recency
                from mart_weekly_311_vs_inspection
                where {area_condition}
            ), selected_weeks as (
                select borough_key, borough_name, week_start_date, total_restaurants
                from recent_areas
                where recency <= {weeks}
            ), complaints_by_area as (
                select dates.week_start_date, complaints.borough_key,
                       count(*) as complaint_count
                from fact_311_complaint as complaints
                join (
                    select date_key, cast(date_trunc('week', calendar_date) as date) as week_start_date
                    from dim_date
                ) as dates on complaints.date_key = dates.date_key
                join dim_complaint_type as types
                    on complaints.complaint_type_key = types.complaint_type_key
                where complaints.borough_key is not null {complaint_filter}
                group by 1, 2

                union all

                select dates.week_start_date, 0 as borough_key,
                       count(*) as complaint_count
                from fact_311_complaint as complaints
                join (
                    select date_key, cast(date_trunc('week', calendar_date) as date) as week_start_date
                    from dim_date
                ) as dates on complaints.date_key = dates.date_key
                join dim_complaint_type as types
                    on complaints.complaint_type_key = types.complaint_type_key
                where 1 = 1 {complaint_filter}
                group by 1
            ), inspections_by_area as (
                select dates.week_start_date, inspections.borough_key,
                       count(*) as inspection_count,
                       sum(inspections.critical_violation_count) as critical_violation_count,
                       sum(case when inspections.has_critical_violation then 1 else 0 end)
                           as inspections_with_critical_violation
                from int_inspection_events as inspections
                join (
                    select date_key, cast(date_trunc('week', calendar_date) as date) as week_start_date
                    from dim_date
                ) as dates on inspections.date_key = dates.date_key
                where inspections.borough_key is not null
                group by 1, 2

                union all

                select dates.week_start_date, 0 as borough_key,
                       count(*) as inspection_count,
                       sum(inspections.critical_violation_count) as critical_violation_count,
                       sum(case when inspections.has_critical_violation then 1 else 0 end)
                           as inspections_with_critical_violation
                from int_inspection_events as inspections
                join (
                    select date_key, cast(date_trunc('week', calendar_date) as date) as week_start_date
                    from dim_date
                ) as dates on inspections.date_key = dates.date_key
                group by 1
            )
            select weeks.week_start_date, weeks.borough_name, weeks.total_restaurants,
                   coalesce(complaints.complaint_count, 0) as complaint_count,
                   coalesce(inspections.inspection_count, 0) as inspection_count,
                   coalesce(inspections.critical_violation_count, 0) as critical_violation_count,
                   coalesce(inspections.inspections_with_critical_violation, 0)
                       as inspections_with_critical_violation,
                   1000.0 * coalesce(complaints.complaint_count, 0)
                       / nullif(weeks.total_restaurants, 0) as complaints_per_1000_restaurants,
                   100.0 * coalesce(inspections.critical_violation_count, 0)
                       / nullif(inspections.inspection_count, 0) as critical_findings_per_100_inspections,
                   100.0 * coalesce(inspections.inspections_with_critical_violation, 0)
                       / nullif(inspections.inspection_count, 0) as inspections_with_critical_per_100
            from selected_weeks as weeks
            left join complaints_by_area as complaints
                on weeks.week_start_date = complaints.week_start_date
                and weeks.borough_key = complaints.borough_key
            left join inspections_by_area as inspections
                on weeks.week_start_date = inspections.week_start_date
                and weeks.borough_key = inspections.borough_key
            order by weeks.borough_name, weeks.week_start_date
            """
        )

    def weekly(
        self, borough: str | None, weeks: int, complaint_type: str | None = None
    ) -> list[dict[str, Any]]:
        borough_name = normalized_borough(borough) or "CITYWIDE"
        return self._weekly_rows(
            f"borough_name = {sql_string(borough_name)}", weeks, complaint_type
        )

    def summary(
        self,
        borough: str | None,
        weeks: int,
        lag_weeks: int,
        complaint_type: str | None = None,
    ) -> dict[str, Any]:
        borough_name = normalized_borough(borough) or "CITYWIDE"
        rows = self.weekly(borough, weeks + lag_weeks, complaint_type)
        complaints = [
            float(row["complaints_per_1000_restaurants"] or 0) for row in rows
        ]
        critical_rates = [
            float(row["inspections_with_critical_per_100"] or 0) for row in rows
        ]
        if lag_weeks:
            complaints = complaints[:-lag_weeks]
            critical_rates = critical_rates[lag_weeks:]
        coefficient = pearson(complaints, critical_rates)
        return describe_correlation(
            borough_name,
            weeks,
            lag_weeks,
            len(complaints),
            coefficient,
            complaint_type,
        )

    def borough_ranking(
        self, weeks: int, lag_weeks: int, complaint_type: str | None = None
    ) -> list[dict[str, Any]]:
        rows = self._weekly_rows(
            "area_level = 'BOROUGH'", weeks + lag_weeks, complaint_type
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["borough_name"]].append(row)

        result = []
        for borough, borough_rows in grouped.items():
            complaints = [
                float(row["complaints_per_1000_restaurants"] or 0)
                for row in borough_rows
            ]
            critical_rates = [
                float(row["inspections_with_critical_per_100"] or 0)
                for row in borough_rows
            ]
            if lag_weeks:
                complaints = complaints[:-lag_weeks]
                critical_rates = critical_rates[lag_weeks:]
            total_restaurants = int(borough_rows[-1]["total_restaurants"])
            complaint_total = sum(
                int(row["complaint_count"])
                for row in borough_rows[: -lag_weeks or None]
            )
            inspection_total = sum(
                int(row["inspection_count"]) for row in borough_rows[lag_weeks:]
            )
            critical_total = sum(
                int(row["critical_violation_count"]) for row in borough_rows[lag_weeks:]
            )
            inspections_with_critical = sum(
                int(row["inspections_with_critical_violation"])
                for row in borough_rows[lag_weeks:]
            )
            coefficient = pearson(complaints, critical_rates)
            result.append(
                {
                    "borough_name": borough,
                    "complaint_count": complaint_total,
                    "complaints_per_1000_restaurants": (
                        1000 * complaint_total / total_restaurants
                        if total_restaurants
                        else None
                    ),
                    "inspection_count": inspection_total,
                    "critical_violation_count": critical_total,
                    "critical_findings_per_100_inspections": (
                        100 * critical_total / inspection_total
                        if inspection_total
                        else None
                    ),
                    "inspections_with_critical_per_100": (
                        100 * inspections_with_critical / inspection_total
                        if inspection_total
                        else None
                    ),
                    "correlation": coefficient,
                    "observations": len(complaints),
                    "confidence_interval": fisher_confidence_interval(
                        coefficient, len(complaints)
                    ),
                }
            )
        return sorted(
            result,
            key=lambda row: row["complaints_per_1000_restaurants"] or 0,
            reverse=True,
        )

    def restaurant_level(self, lookback_days: int = 28) -> dict[str, Any]:
        rows = self.athena.query(
            f"""
            with inspections as (
                select events.inspection_id, events.restaurant_key,
                       dates.calendar_date as inspection_date,
                       events.has_critical_violation
                from int_inspection_events as events
                join dim_date as dates on events.date_key = dates.date_key
                where events.restaurant_key is not null
            ), matched_complaints as (
                select complaints.complaint_id, complaints.restaurant_key,
                       dates.calendar_date as complaint_date
                from fact_311_complaint as complaints
                join dim_date as dates on complaints.date_key = dates.date_key
                where complaints.restaurant_key is not null
                  and complaints.restaurant_match_status = 'MATCHED'
            ), inspection_features as (
                select inspections.inspection_id,
                       inspections.has_critical_violation,
                       count(complaints.complaint_id) as prior_complaint_count
                from inspections
                left join matched_complaints as complaints
                    on inspections.restaurant_key = complaints.restaurant_key
                    and complaints.complaint_date < inspections.inspection_date
                    and complaints.complaint_date >= date_add(
                        'day', -{lookback_days}, inspections.inspection_date
                    )
                group by inspections.inspection_id, inspections.has_critical_violation
            )
            select count(*) as inspections_analyzed,
                   sum(case when prior_complaint_count > 0 then 1 else 0 end)
                       as inspections_with_prior_complaint,
                   100.0 * avg(case when prior_complaint_count > 0 and has_critical_violation then 1.0
                                    when prior_complaint_count > 0 then 0.0 end)
                       as critical_rate_with_prior_complaint,
                   100.0 * avg(case when prior_complaint_count = 0 and has_critical_violation then 1.0
                                    when prior_complaint_count = 0 then 0.0 end)
                       as critical_rate_without_prior_complaint,
                   corr(cast(prior_complaint_count as double),
                        case when has_critical_violation then 1.0 else 0.0 end)
                       as complaint_critical_correlation
            from inspection_features
            """
        )
        result = rows[0] if rows else {}
        with_rate = result.get("critical_rate_with_prior_complaint")
        without_rate = result.get("critical_rate_without_prior_complaint")
        result["lookback_days"] = lookback_days
        result["critical_rate_difference_points"] = (
            float(with_rate) - float(without_rate)
            if with_rate is not None and without_rate is not None
            else None
        )
        return result


def pearson(left: list[float], right: list[float]) -> float | None:
    """Return Pearson correlation, or null when it would be misleading."""
    if len(left) < 3 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def fisher_confidence_interval(
    coefficient: float | None, observations: int
) -> list[float] | None:
    if coefficient is None or observations <= 3 or abs(coefficient) >= 1:
        return None
    transformed = math.atanh(coefficient)
    margin = 1.96 / math.sqrt(observations - 3)
    return [
        round(math.tanh(transformed - margin), 6),
        round(math.tanh(transformed + margin), 6),
    ]


def describe_correlation(
    borough: str,
    weeks: int,
    lag_weeks: int,
    observations: int,
    coefficient: float | None,
    complaint_type: str | None = None,
) -> dict[str, Any]:
    interval = fisher_confidence_interval(coefficient, observations)
    if coefficient is None:
        return {
            "borough": borough,
            "weeks": weeks,
            "lag_weeks": lag_weeks,
            "observations": observations,
            "coefficient": None,
            "confidence_interval": interval,
            "complaint_type": normalized_complaint_type(complaint_type) or "ALL",
            "direction": "not_calculable",
            "strength": "not calculable",
            "is_calculable": False,
        }
    absolute = abs(coefficient)
    if absolute < 0.3:
        strength = "weak"
    elif absolute < 0.6:
        strength = "moderate"
    else:
        strength = "strong"
    direction = (
        "positive" if coefficient > 0 else "negative" if coefficient < 0 else "none"
    )
    return {
        "borough": borough,
        "weeks": weeks,
        "lag_weeks": lag_weeks,
        "observations": observations,
        "coefficient": round(coefficient, 6),
        "confidence_interval": interval,
        "complaint_type": normalized_complaint_type(complaint_type) or "ALL",
        "direction": direction,
        "strength": strength,
        "is_calculable": True,
    }
