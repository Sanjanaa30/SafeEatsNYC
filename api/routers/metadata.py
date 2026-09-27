"""Metadata, filter values, and data-freshness endpoints."""

from fastapi import APIRouter, Depends

from api.dependencies import get_metadata_service
from api.routers.errors import safely
from api.schemas.dashboard import (
    CollectionResponse,
    DataFreshnessResponse,
    MetadataResponse,
)
from api.services.metadata import MetadataService
from api.services.sql import BOROUGHS

router = APIRouter(tags=["metadata"])


@router.get("/metadata", response_model=MetadataResponse)
def metadata(service: MetadataService = Depends(get_metadata_service)) -> dict:
    return safely(service.metadata)


@router.get("/data-freshness", response_model=DataFreshnessResponse)
def data_freshness(
    service: MetadataService = Depends(get_metadata_service),
) -> dict:
    return safely(service.freshness)


@router.get("/boroughs", response_model=CollectionResponse)
def boroughs() -> CollectionResponse:
    items = [{"borough_name": value} for value in BOROUGHS]
    return CollectionResponse(items=items, total=len(items))


@router.get("/cuisines", response_model=CollectionResponse)
def cuisines(
    service: MetadataService = Depends(get_metadata_service),
) -> CollectionResponse:
    values = safely(service.cuisines)
    return CollectionResponse(
        items=[{"cuisine": value} for value in values], total=len(values)
    )
