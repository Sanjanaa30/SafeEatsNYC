"""Current restaurant risk-score endpoints backed by approved S3 output."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_restaurant_service, get_risk_score_service
from api.routers.errors import safely
from api.schemas.dashboard import RecordResponse, RiskCollectionResponse, RiskRecord
from api.services.restaurants import RestaurantService
from api.services.risk import RiskScoreService
from api.services.sql import normalized_borough, validated_key

router = APIRouter(prefix="/risk", tags=["risk"])


def joined_scores(
    risk_service: RiskScoreService,
    restaurant_service: RestaurantService,
) -> list[dict]:
    scores = safely(risk_service.load)
    metadata = {
        row["restaurant_key"]: row
        for row in safely(restaurant_service.metadata_snapshot)
    }
    result = []
    for score in scores:
        restaurant = metadata.get(score["restaurant_key"], {})
        result.append({**score, **restaurant})
    return result


@router.get("/top", response_model=RiskCollectionResponse)
def top_risk(
    limit: int = Query(20, ge=1, le=100),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> RiskCollectionResponse:
    rows = joined_scores(risk_service, restaurant_service)
    rows.sort(key=lambda row: row["risk_probability"], reverse=True)
    selected = rows[:limit]
    return RiskCollectionResponse(
        items=[RiskRecord.model_validate(row) for row in selected],
        total=len(rows),
        page=1,
        page_size=limit,
    )


@router.get("/restaurants", response_model=RiskCollectionResponse)
def risk_restaurants(
    query: str | None = Query(None, min_length=2, max_length=80),
    borough: str | None = None,
    cuisine: str | None = Query(None, min_length=1, max_length=100),
    category: Literal["LOW", "MODERATE", "HIGH"] | None = None,
    sort: Literal["risk", "name", "inspection_date"] = "risk",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> RiskCollectionResponse:
    borough = normalized_borough(borough)
    rows = joined_scores(risk_service, restaurant_service)
    if query:
        search = query.strip().upper()
        rows = [
            row
            for row in rows
            if search in str(row.get("restaurant_name") or "").upper()
            or search in str(row.get("restaurant_id") or "")
        ]
    if borough:
        rows = [row for row in rows if row.get("borough_name") == borough]
    if cuisine:
        rows = [row for row in rows if row.get("cuisine") == cuisine]
    if category:
        rows = [row for row in rows if row["risk_category"] == category]
    sort_key = {
        "risk": lambda row: row["risk_probability"],
        "name": lambda row: str(row.get("restaurant_name") or ""),
        "inspection_date": lambda row: str(row.get("latest_inspection_date") or ""),
    }[sort]
    rows.sort(key=sort_key, reverse=direction == "desc")
    total = len(rows)
    offset = (page - 1) * page_size
    selected = rows[offset : offset + page_size]
    return RiskCollectionResponse(
        items=[RiskRecord.model_validate(row) for row in selected],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/restaurants/{restaurant_key}", response_model=RecordResponse)
def restaurant_risk(
    restaurant_key: str,
    risk_service: RiskScoreService = Depends(get_risk_score_service),
    restaurant_service: RestaurantService = Depends(get_restaurant_service),
) -> RecordResponse:
    key = validated_key(restaurant_key, "Restaurant key")
    score = safely(risk_service.by_restaurant_key).get(key)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approved risk score exists for this restaurant.",
        )
    restaurant = safely(lambda: restaurant_service.detail(key)) or {}
    return RecordResponse(data={**score, **restaurant})
