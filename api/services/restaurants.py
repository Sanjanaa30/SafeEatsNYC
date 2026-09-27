"""Restaurant search, history, violation, and nearby queries."""

import math
import re
from typing import Any

from api.services.athena import AthenaQueryService
from api.services.presentation import (
    REPEATED_CRITICAL_COLUMNS,
    REPEATED_CRITICAL_CTES,
)
from api.services.sql import normalized_borough, sql_string, validated_key

SEARCH_STOP_WORDS = {"AT", "IN", "NY", "NYC", "ON"}
SEARCH_EXPRESSION = """
    upper(concat_ws(' ',
        coalesce(r.restaurant_name, ''),
        coalesce(r.restaurant_name_normalized, ''),
        coalesce(r.camis, ''),
        coalesce(r.address, ''),
        coalesce(r.zipcode, ''),
        coalesce(b.borough_name, ''),
        coalesce(r.cuisine, '')
    ))
"""
SORT_COLUMNS = {
    "name": "r.restaurant_name",
    "grade": "h.grade",
    "score": "h.score",
    "inspection_date": "h.inspection_date",
    "days_since_inspection": "h.days_since_inspection",
}
FLAG_FILTERS = {
    "chain": ["r.is_chain"],
    "independent": ["not r.is_chain"],
    "fast_food": ["r.is_confirmed_fast_food"],
    "recently_improved": [
        "not r.is_chain",
        "h.improved_to_a",
        "h.inspection_date >= date_add('day', -90, current_date)",
    ],
    "repeat_critical": [
        "not r.is_chain",
        "repeats.has_repeated_critical_violation",
    ],
}


def _search_terms(query: str) -> list[str]:
    """Return useful words from a free-text restaurant search."""
    return [
        term
        for term in re.findall(r"[A-Z0-9]+", query.upper())
        if len(term) > 1 and term not in SEARCH_STOP_WORDS
    ]


def _restaurant_filters(
    *,
    query: str | None,
    borough: str | None,
    cuisine: str | None,
    grade: str | None,
    flag: str | None,
) -> list[str]:
    """Build the SQL conditions shared by restaurant rows and their count."""
    filters = []

    if query:
        filters.extend(
            f"{SEARCH_EXPRESSION} like {sql_string(f'%{term}%')}"
            for term in _search_terms(query)
        )
    if borough:
        filters.append(f"b.borough_name = {sql_string(borough)}")
    if cuisine:
        filters.append(f"r.cuisine = {sql_string(cuisine.strip())}")
    if grade:
        filters.append(f"h.grade = {sql_string(grade)}")
    filters.extend(FLAG_FILTERS.get(flag or "", []))

    return filters


class RestaurantService:
    def __init__(self, athena: AthenaQueryService) -> None:
        self.athena = athena

    def search(
        self,
        *,
        query: str | None,
        borough: str | None,
        cuisine: str | None,
        grade: str | None,
        flag: str | None,
        sort: str,
        direction: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        borough = normalized_borough(borough)
        filters = _restaurant_filters(
            query=query,
            borough=borough,
            cuisine=cuisine,
            grade=grade,
            flag=flag,
        )
        order_column = SORT_COLUMNS[sort]
        where = " and ".join(filters) if filters else "1 = 1"
        offset = (page - 1) * page_size
        columns = f"""
            r.restaurant_key, r.camis as restaurant_id, r.restaurant_name,
            r.address, r.zipcode, r.nta_name, b.borough_name, r.cuisine,
            r.latitude, r.longitude, h.grade as current_grade,
            h.score as current_score, h.inspection_date as latest_inspection_date,
            h.days_since_inspection, h.is_grade_consistent, h.improved_to_a,
            r.is_chain, r.is_confirmed_fast_food, r.chain_key,
            coalesce(
                trend.three_year_grades,
                cast(array[] as array(varchar))
            ) as three_year_grades,
            {REPEATED_CRITICAL_COLUMNS}
        """
        rows = self.athena.query(
            f"""
            with {REPEATED_CRITICAL_CTES},
            latest_grade_by_year as (
                select
                    restaurant_key,
                    year(inspection_date) as grade_year,
                    max_by(grade, inspection_date) as grade
                from mart_restaurant_grade_history
                where inspection_date >= date_add(
                    'year', -2, date_trunc('year', current_date)
                )
                group by restaurant_key, year(inspection_date)
            ),
            three_year_grade_trend as (
                select
                    restaurant_key,
                    array_agg(grade order by grade_year) as three_year_grades
                from latest_grade_by_year
                group by restaurant_key
            )
            select {columns}
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            left join mart_restaurant_grade_history h
              on r.restaurant_key = h.restaurant_key
             and h.inspection_recency_rank = 1
            left join three_year_grade_trend trend
              on r.restaurant_key = trend.restaurant_key
            left join repeated_critical_summary repeats
              on r.restaurant_key = repeats.restaurant_key
            where {where}
            order by {order_column} {direction}, r.restaurant_key
            offset {offset} rows fetch next {page_size} rows only
            """
        )
        count = self.athena.query(
            f"""
            with {REPEATED_CRITICAL_CTES}
            select count(*) as total
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            left join mart_restaurant_grade_history h
              on r.restaurant_key = h.restaurant_key
             and h.inspection_recency_rank = 1
            left join repeated_critical_summary repeats
              on r.restaurant_key = repeats.restaurant_key
            where {where}
            """
        )[0]["total"]
        return rows, int(count)

    def detail(self, restaurant_key: str) -> dict[str, Any] | None:
        key = validated_key(restaurant_key, "Restaurant key")
        rows = self.athena.query(
            f"""
            with {REPEATED_CRITICAL_CTES}
            select r.restaurant_key, r.camis as restaurant_id, r.restaurant_name,
                   r.restaurant_name_normalized, r.address, r.zipcode, r.nta_code,
                   r.nta_name, b.borough_name, r.cuisine, r.latitude, r.longitude,
                   r.coordinate_status, r.is_chain, r.is_confirmed_fast_food,
                   r.is_reviewed_co_brand, r.fast_food_brand_names, r.chain_key,
                   h.grade as current_grade, h.score as current_score,
                   h.inspection_date as latest_inspection_date,
                   h.days_since_inspection, h.graded_inspection_count,
                   h.is_grade_consistent, h.is_consistently_grade_a,
                   h.improved_to_a,
                   {REPEATED_CRITICAL_COLUMNS}
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            left join mart_restaurant_grade_history h
              on r.restaurant_key = h.restaurant_key
             and h.inspection_recency_rank = 1
            left join repeated_critical_summary repeats
              on r.restaurant_key = repeats.restaurant_key
            where r.restaurant_key = {sql_string(key)}
            limit 1
            """
        )
        return rows[0] if rows else None

    def history(self, restaurant_key: str) -> list[dict[str, Any]]:
        key = validated_key(restaurant_key, "Restaurant key")
        return self.athena.query(
            f"""
            select inspection_id, inspection_date, grade, previous_grade, score,
                   violation_count, critical_violation_count,
                   has_critical_violation, improved_to_a
            from mart_restaurant_grade_history
            where restaurant_key = {sql_string(key)}
            order by inspection_date desc, inspection_id desc
            """
        )

    def violations(self, restaurant_key: str, limit: int) -> list[dict[str, Any]]:
        key = validated_key(restaurant_key, "Restaurant key")
        return self.athena.query(
            f"""
            select f.inspection_id, d.calendar_date as inspection_date,
                   v.violation_code, v.violation_description, v.is_critical
            from fact_inspection f
            join dim_date d on f.date_key = d.date_key
            join dim_violation v on f.violation_key = v.violation_key
            where f.restaurant_key = {sql_string(key)}
            order by d.calendar_date desc, v.is_critical desc, v.violation_code
            limit {limit}
            """
        )

    def recently_improved(self, limit: int) -> list[dict[str, Any]]:
        return self.athena.query(
            f"""
            select restaurant_key, camis as restaurant_id, restaurant_name,
                   borough_name, cuisine, inspection_date, previous_grade,
                   grade as current_grade
            from mart_restaurant_grade_history
            where inspection_recency_rank = 1 and improved_to_a
              and inspection_date >= date_add('day', -90, current_date)
            order by inspection_date desc, restaurant_name
            limit {limit}
            """
        )

    def nearby(
        self,
        restaurant_key: str,
        radius_meters: int,
        same_cuisine: bool,
        independent_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        selected = self.detail(restaurant_key)
        if not selected:
            return []
        latitude = selected.get("latitude")
        longitude = selected.get("longitude")
        if latitude is None or longitude is None:
            return []
        latitude = float(latitude)
        longitude = float(longitude)
        latitude_delta = radius_meters / 111_320
        longitude_delta = radius_meters / (
            111_320 * max(math.cos(math.radians(latitude)), 0.01)
        )
        filters = [
            "h.inspection_recency_rank = 1",
            "h.grade = 'A'",
            f"h.restaurant_key <> {sql_string(restaurant_key)}",
            f"h.latitude between {latitude - latitude_delta} and {latitude + latitude_delta}",
            f"h.longitude between {longitude - longitude_delta} and {longitude + longitude_delta}",
        ]
        if same_cuisine and selected.get("cuisine"):
            filters.append(f"h.cuisine = {sql_string(selected['cuisine'])}")
        if independent_only:
            filters.append("not h.is_chain")
        where = " and ".join(filters)
        distance = f"""
            6371000 * 2 * asin(sqrt(
                pow(sin(radians(h.latitude - {latitude}) / 2), 2)
                + cos(radians({latitude})) * cos(radians(h.latitude))
                * pow(sin(radians(h.longitude - {longitude}) / 2), 2)
            ))
        """
        return self.athena.query(
            f"""
            select * from (
                select h.restaurant_key, h.camis as restaurant_id,
                       h.restaurant_name, h.address, h.borough_name, h.cuisine,
                       h.grade as current_grade,
                       h.inspection_date as latest_inspection_date,
                       {distance} as distance_meters
                from mart_restaurant_grade_history h
                where {where}
            ) nearby
            where distance_meters <= {radius_meters}
            order by distance_meters
            limit {limit}
            """
        )

    def metadata_snapshot(self) -> list[dict[str, Any]]:
        return self.athena.query(
            f"""
            with {REPEATED_CRITICAL_CTES}
            select r.restaurant_key, r.camis as restaurant_id, r.restaurant_name,
                   r.address, b.borough_name, r.cuisine,
                   r.chain_key,
                   h.grade as current_grade,
                   h.inspection_date as latest_inspection_date,
                   {REPEATED_CRITICAL_COLUMNS}
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            left join mart_restaurant_grade_history h
             on r.restaurant_key = h.restaurant_key
             and h.inspection_recency_rank = 1
            left join repeated_critical_summary repeats
              on r.restaurant_key = repeats.restaurant_key
            """,
            cache_key="restaurant-metadata-snapshot",
        )
