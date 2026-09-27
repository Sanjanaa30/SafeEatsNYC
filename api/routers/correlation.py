"""Weekly correlation, summary, ranking, and map endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_correlation_service
from api.routers.errors import safely
from api.schemas.dashboard import (
    CollectionResponse,
    CorrelationSummaryResponse,
    RecordResponse,
)
from api.services.correlation import CorrelationService

router = APIRouter(prefix="/correlation", tags=["correlation"])


def validate_period(weeks: int, lag_weeks: int = 0) -> None:
    if weeks not in {8, 12, 26, 52, 104}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Weeks must be 8, 12, 26, 52, or 104.",
        )
    if lag_weeks not in {0, 1, 2, 4, 8}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Lag weeks must be 0, 1, 2, 4, or 8.",
        )


@router.get("/weekly", response_model=CollectionResponse)
def weekly(
    borough: str | None = None,
    weeks: int = Query(12, ge=1, le=104),
    complaint_type: str | None = None,
    service: CorrelationService = Depends(get_correlation_service),
) -> CollectionResponse:
    validate_period(weeks)
    rows = safely(lambda: service.weekly(borough, weeks, complaint_type))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/summary", response_model=CorrelationSummaryResponse)
def summary(
    borough: str | None = None,
    weeks: int = Query(12, ge=1, le=104),
    lag_weeks: int = Query(2, ge=0, le=8),
    complaint_type: str | None = None,
    service: CorrelationService = Depends(get_correlation_service),
) -> dict:
    validate_period(weeks, lag_weeks)
    return safely(lambda: service.summary(borough, weeks, lag_weeks, complaint_type))


@router.get("/borough-ranking", response_model=CollectionResponse)
def borough_ranking(
    weeks: int = Query(12, ge=1, le=104),
    lag_weeks: int = Query(2, ge=0, le=8),
    complaint_type: str | None = None,
    service: CorrelationService = Depends(get_correlation_service),
) -> CollectionResponse:
    validate_period(weeks, lag_weeks)
    rows = safely(lambda: service.borough_ranking(weeks, lag_weeks, complaint_type))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/map", response_model=CollectionResponse)
def map_values(
    metric: Literal["complaints", "failures", "overlap"] = "overlap",
    weeks: int = Query(12, ge=1, le=104),
    lag_weeks: int = Query(2, ge=0, le=8),
    complaint_type: str | None = None,
    service: CorrelationService = Depends(get_correlation_service),
) -> CollectionResponse:
    validate_period(weeks, lag_weeks)
    rows = safely(lambda: service.borough_ranking(weeks, lag_weeks, complaint_type))
    max_complaints = (
        max(
            (item.get("complaints_per_1000_restaurants") or 0 for item in rows),
            default=1,
        )
        or 1
    )
    max_failures = (
        max(
            (item.get("inspections_with_critical_per_100") or 0 for item in rows),
            default=1,
        )
        or 1
    )
    for row in rows:
        complaints = row.get("complaints_per_1000_restaurants") or 0
        failures = row.get("inspections_with_critical_per_100") or 0
        row["metric"] = metric
        row["metric_value"] = {
            "complaints": complaints,
            "failures": failures,
            "overlap": min(
                100 * complaints / max_complaints, 100 * failures / max_failures
            ),
        }[metric]
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/restaurant-level", response_model=RecordResponse)
def restaurant_level(
    lookback_days: int = Query(28, ge=7, le=90),
    service: CorrelationService = Depends(get_correlation_service),
) -> RecordResponse:
    return RecordResponse(data=safely(lambda: service.restaurant_level(lookback_days)))
