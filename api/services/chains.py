"""Chain summaries and individual chain-location queries."""

from typing import Any

from api.services.athena import AthenaQueryService
from api.services.sql import normalized_borough, sql_string, validated_key


class ChainService:
    def __init__(self, athena: AthenaQueryService) -> None:
        self.athena = athena

    def search(
        self,
        *,
        query: str | None,
        borough: str | None,
        confirmed_fast_food_only: bool,
    ) -> tuple[list[dict[str, Any]], int]:
        borough = normalized_borough(borough)
        filters = []
        if confirmed_fast_food_only:
            filters.append("is_confirmed_fast_food")
        if query:
            filters.append(
                f"upper(chain_name) like {sql_string('%' + query.strip().upper() + '%')}"
            )
        if borough:
            filters.append(f"contains(boroughs_present, {sql_string(borough)})")
        where = " and ".join(filters) if filters else "1 = 1"
        rows = self.athena.query(
            f"""
            select chain_key, chain_name, location_count, borough_count,
                   is_confirmed_fast_food, cuisines, boroughs_present,
                   confirmed_fast_food_brands, graded_location_count,
                   grade_a_location_count, grade_b_location_count,
                   grade_c_location_count, ungraded_location_count,
                   grade_a_percent_of_graded_locations, average_latest_score,
                   best_current_grade, worst_current_grade
            from mart_chain_summary
            where {where}
            """
        )
        return rows, len(rows)

    def detail(self, chain_key: str) -> dict[str, Any] | None:
        key = validated_key(chain_key, "Chain key")
        rows = self.athena.query(
            f"select * from mart_chain_summary where chain_key = {sql_string(key)} limit 1"
        )
        return rows[0] if rows else None

    def locations(self, chain_key: str, borough: str | None) -> list[dict[str, Any]]:
        key = validated_key(chain_key, "Chain key")
        borough = normalized_borough(borough)
        borough_filter = (
            f"and b.borough_name = {sql_string(borough)}" if borough else ""
        )
        return self.athena.query(
            f"""
            select r.restaurant_key, r.camis as restaurant_id, r.restaurant_name,
                   r.address, r.zipcode, r.nta_name, b.borough_name, r.cuisine,
                   r.latitude, r.longitude, r.is_reviewed_co_brand,
                   r.fast_food_brand_names, h.grade as current_grade,
                   h.score as current_score,
                   h.inspection_date as latest_inspection_date
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            left join mart_restaurant_grade_history h
              on r.restaurant_key = h.restaurant_key
             and h.inspection_recency_rank = 1
            where r.chain_key = {sql_string(key)} {borough_filter}
            order by b.borough_name, r.restaurant_name, r.camis
            """
        )
