"""Restaurant finder, detail, history, and nearby endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_restaurant_service, get_risk_score_service
from api.routers.errors import safely
from api.schemas.dashboard import CollectionResponse, RecordResponse
from api.services.restaurants import RestaurantService
from api.services.risk import RiskScoreService

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def attach_risk(rows: list[dict], risk_service: RiskScoreService) -> list[dict]:
    scores = safely(risk_service.by_restaurant_key)
    for row in rows:
        score = scores.get(row["restaurant_key"])
        row["risk_probability"] = score.get("risk_probability") if score else None
        row["risk_category"] = score.get("risk_category") if score else None
    return rows


@router.get("/recently-improved", response_model=CollectionResponse)
def recently_improved(
    limit: int = Query(10, ge=1, le=50),
    service: RestaurantService = Depends(get_restaurant_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
) -> CollectionResponse:
    rows = safely(lambda: service.recently_improved(limit))
    attach_risk(rows, risk_service)
    return CollectionResponse(items=rows, total=len(rows))


@router.get("", response_model=CollectionResponse)
def restaurants(
    query: str | None = Query(None, min_length=2, max_length=80),
    borough: str | None = None,
    cuisine: str | None = Query(None, min_length=1, max_length=100),
    grade: Literal["A", "B", "C"] | None = None,
    flag: Literal[
        "chain", "independent", "fast_food", "recently_improved", "repeat_critical"
    ]
    | None = None,
    sort: Literal[
        "name", "grade", "score", "inspection_date", "days_since_inspection"
    ] = "name",
    direction: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: RestaurantService = Depends(get_restaurant_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
) -> CollectionResponse:
    rows, total = safely(
        lambda: service.search(
            query=query,
            borough=borough,
            cuisine=cuisine,
            grade=grade,
            flag=flag,
            sort=sort,
            direction=direction,
            page=page,
            page_size=page_size,
        )
    )
    attach_risk(rows, risk_service)
    return CollectionResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{restaurant_key}", response_model=RecordResponse)
def restaurant(
    restaurant_key: str,
    service: RestaurantService = Depends(get_restaurant_service),
    risk_service: RiskScoreService = Depends(get_risk_score_service),
) -> RecordResponse:
    row = safely(lambda: service.detail(restaurant_key))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found."
        )
    score = safely(risk_service.by_restaurant_key).get(restaurant_key)
    if score:
        row["risk"] = score
    return RecordResponse(data=row)


@router.get("/{restaurant_key}/history", response_model=CollectionResponse)
def history(
    restaurant_key: str,
    service: RestaurantService = Depends(get_restaurant_service),
) -> CollectionResponse:
    rows = safely(lambda: service.history(restaurant_key))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/{restaurant_key}/violations", response_model=CollectionResponse)
def violations(
    restaurant_key: str,
    limit: int = Query(100, ge=1, le=500),
    service: RestaurantService = Depends(get_restaurant_service),
) -> CollectionResponse:
    rows = safely(lambda: service.violations(restaurant_key, limit))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/{restaurant_key}/nearby", response_model=CollectionResponse)
def nearby(
    restaurant_key: str,
    radius_meters: int = Query(1000, ge=100, le=5000),
    same_cuisine: bool = False,
    independent_only: bool = False,
    limit: int = Query(10, ge=1, le=50),
    service: RestaurantService = Depends(get_restaurant_service),
) -> CollectionResponse:
    rows = safely(
        lambda: service.nearby(
            restaurant_key,
            radius_meters,
            same_cuisine,
            independent_only,
            limit,
        )
    )
    return CollectionResponse(items=rows, total=len(rows))
