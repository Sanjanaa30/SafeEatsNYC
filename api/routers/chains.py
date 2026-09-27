"""Chain summary and per-location endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import (
    get_chain_service,
    get_restaurant_service,
    get_risk_score_service,
)
from api.routers.errors import safely
from api.schemas.dashboard import CollectionResponse, RecordResponse
from api.services.chains import ChainService
from api.services.restaurants import RestaurantService
from api.services.risk import RiskScoreService

router = APIRouter(prefix="/chains", tags=["chains"])


def chain_risk_rollups(
    risk_service: RiskScoreService,
    locations: list[dict],
) -> dict[str, dict]:
    """Aggregate location-level scores and repeat flags without losing co-brands."""

    scores = safely(risk_service.by_restaurant_key)
    grouped: dict[str, list[dict]] = {}
    for location in locations:
        chain_key = location.get("chain_key")
        if chain_key:
            grouped.setdefault(chain_key, []).append(location)

    result = {}
    for chain_key, chain_locations in grouped.items():
        scored = [
            (location, scores[location["restaurant_key"]])
            for location in chain_locations
            if location["restaurant_key"] in scores
        ]
        highest = max(
            scored, key=lambda item: item[1]["risk_probability"], default=None
        )
        probabilities = [score["risk_probability"] for _, score in scored]
        result[chain_key] = {
            "average_risk_probability": (
                sum(probabilities) / len(probabilities) if probabilities else None
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
                for location in chain_locations
            ),
        }
    return result


@router.get("", response_model=CollectionResponse)
def chains(
    query: str | None = Query(None, min_length=2, max_length=80),
    borough: str | None = None,
    confirmed_fast_food_only: bool = True,
    sort: Literal[
        "name", "location_count", "worst_grade", "average_score", "average_risk"
    ] = "name",
    direction: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ChainService = Depends(get_chain_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> CollectionResponse:
    rows, total = safely(
        lambda: service.search(
            query=query,
            borough=borough,
            confirmed_fast_food_only=confirmed_fast_food_only,
        )
    )
    rollups = chain_risk_rollups(
        risk_service, safely(restaurant_service.metadata_snapshot)
    )
    for row in rows:
        row.update(
            rollups.get(
                row["chain_key"],
                {
                    "average_risk_probability": None,
                    "high_risk_location_count": 0,
                    "highest_risk_location": None,
                    "has_repeated_critical_location": False,
                },
            )
        )
    reverse = direction == "desc"
    sort_key = {
        "name": lambda row: str(row.get("chain_name") or ""),
        "location_count": lambda row: row.get("location_count") or 0,
        "worst_grade": lambda row: {"A": 1, "B": 2, "C": 3}.get(
            row.get("worst_current_grade"), 0
        ),
        "average_score": lambda row: row.get("average_latest_score") or -1,
        "average_risk": lambda row: row.get("average_risk_probability") or -1,
    }[sort]
    rows.sort(key=sort_key, reverse=reverse)
    offset = (page - 1) * page_size
    return CollectionResponse(
        items=rows[offset : offset + page_size],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{chain_key}", response_model=RecordResponse)
def chain(
    chain_key: str,
    service: ChainService = Depends(get_chain_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> RecordResponse:
    row = safely(lambda: service.detail(chain_key))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found."
        )
    all_locations = safely(restaurant_service.metadata_snapshot)
    row.update(chain_risk_rollups(risk_service, all_locations).get(chain_key, {}))
    return RecordResponse(data=row)


@router.get("/{chain_key}/locations", response_model=CollectionResponse)
def locations(
    chain_key: str,
    borough: str | None = None,
    service: ChainService = Depends(get_chain_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> CollectionResponse:
    rows = safely(lambda: service.locations(chain_key, borough))
    scores = safely(risk_service.by_restaurant_key)
    metadata = {
        item["restaurant_key"]: item
        for item in safely(restaurant_service.metadata_snapshot)
    }
    for row in rows:
        score = scores.get(row["restaurant_key"])
        row["risk_probability"] = score.get("risk_probability") if score else None
        row["risk_category"] = score.get("risk_category") if score else None
        summary = metadata.get(row["restaurant_key"], {})
        row["has_repeated_critical_violation"] = summary.get(
            "has_repeated_critical_violation", False
        )
        row["repeated_critical_codes"] = summary.get("repeated_critical_codes", [])
    return CollectionResponse(items=rows, total=len(rows))
