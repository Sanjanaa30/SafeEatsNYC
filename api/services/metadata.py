"""Filter metadata and truthful warehouse/model freshness information."""

from typing import Any

from api.config import Settings
from api.services.athena import AthenaQueryService
from api.services.risk import RiskScoreService
from api.services.sql import BOROUGHS


class MetadataService:
    def __init__(
        self,
        athena: AthenaQueryService,
        risk: RiskScoreService,
        settings: Settings,
    ) -> None:
        self.athena = athena
        self.risk = risk
        self.settings = settings

    def freshness(self, score_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        warehouse = self.athena.query(
            """
            select
                (select cast(min(calendar_date) as varchar)
                 from fact_inspection f join dim_date d on f.date_key = d.date_key)
                    as earliest_inspection_date,
                (select cast(max(calendar_date) as varchar)
                 from fact_inspection f join dim_date d on f.date_key = d.date_key)
                    as latest_inspection_date,
                (select cast(max(created_date) as varchar)
                 from fact_311_complaint) as latest_complaint_date
            """,
            cache_key="data-freshness",
        )[0]
        score_summary = score_summary or self.risk.summary()
        return {
            **warehouse,
            "latest_ml_scoring_timestamp": score_summary.get("scoring_timestamp"),
            "risk_score_run_id": score_summary.get("score_run_id"),
            "refresh_description": "Latest completed warehouse snapshot; not live data.",
        }

    def cuisines(self) -> list[str]:
        rows = self.athena.query(
            "select distinct cuisine from dim_restaurant where cuisine is not null order by cuisine",
            cache_key="metadata-cuisines",
        )
        return [row["cuisine"] for row in rows]

    def metadata(self) -> dict[str, Any]:
        score_summary = self.risk.summary()
        return {
            "status": "ok",
            "boroughs": list(BOROUGHS),
            "cuisines": self.cuisines(),
            "model_version": score_summary.get("model_version"),
            "data_freshness": self.freshness(score_summary),
        }
