"""Citywide and borough overview endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_overview_service
from api.routers.errors import safely
from api.schemas.dashboard import CollectionResponse
from api.services.overview import OverviewService

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/kpis", response_model=CollectionResponse)
def kpis(
    borough: str | None = None,
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(lambda: service.kpis(borough))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/boroughs", response_model=CollectionResponse)
def boroughs(
    sort: Literal[
        "safety_rank",
        "grade_a_percent",
        "complaint_rate",
        "critical_violation_rate",
        "improvement_rate",
        "total_restaurants",
        "name",
    ] = "safety_rank",
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(lambda: service.boroughs(sort))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/grades", response_model=CollectionResponse)
def grades(
    borough: str | None = None,
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(lambda: service.grades(borough))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/grade-distribution", response_model=CollectionResponse)
def grade_distribution(
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(service.grade_distribution_by_borough)
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/cuisine-heatmap", response_model=CollectionResponse)
def cuisine_heatmap(
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(service.cuisine_heatmap)
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/cuisines", response_model=CollectionResponse)
def cuisines(
    borough: str | None = None,
    sort: Literal["name", "grade_a_percent", "total_restaurants"] = "grade_a_percent",
    limit: int = Query(15, ge=1, le=20),
    minimum_restaurants: int = Query(10, ge=1, le=1000),
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(lambda: service.cuisines(borough, sort, limit, minimum_restaurants))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/violations", response_model=CollectionResponse)
def violations(
    borough: str | None = None,
    criticality: Literal["all", "critical", "non_critical"] = "all",
    sort: Literal["frequency", "critical_first", "name"] = "frequency",
    limit: int = Query(15, ge=1, le=100),
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(lambda: service.violations(borough, criticality, sort, limit))
    return CollectionResponse(items=rows, total=len(rows))


@router.get("/violation-criticality-by-borough", response_model=CollectionResponse)
def violation_criticality_by_borough(
    service: OverviewService = Depends(get_overview_service),
) -> CollectionResponse:
    rows = safely(service.violation_criticality_by_borough)
    return CollectionResponse(items=rows, total=len(rows))
