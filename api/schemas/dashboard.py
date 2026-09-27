"""Response models shared by the Phase 7 dashboard endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CollectionResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class RecordResponse(BaseModel):
    data: dict[str, Any]


class DataFreshnessResponse(BaseModel):
    earliest_inspection_date: str | None = None
    latest_inspection_date: str | None
    latest_complaint_date: str | None
    latest_ml_scoring_timestamp: str | None
    risk_score_run_id: str
    refresh_description: str


class MetadataResponse(BaseModel):
    status: Literal["ok"]
    boroughs: list[str]
    cuisines: list[str]
    model_version: str | None
    data_freshness: DataFreshnessResponse


class CorrelationSummaryResponse(BaseModel):
    borough: str
    weeks: int
    lag_weeks: int
    observations: int
    coefficient: float | None
    confidence_interval: list[float] | None = None
    complaint_type: str = "ALL"
    direction: Literal["positive", "negative", "none", "not_calculable"]
    strength: Literal["weak", "moderate", "strong", "not calculable"]
    is_calculable: bool


class RiskFactor(BaseModel):
    feature: str
    contribution: float
    direction: str | None = None


class RiskRecord(BaseModel):
    restaurant_key: str
    restaurant_id: str | None = None
    restaurant_name: str | None = None
    address: str | None = None
    borough_name: str | None = None
    cuisine: str | None = None
    current_grade: str | None = None
    latest_inspection_date: str | None = None
    risk_probability: float = Field(ge=0, le=1)
    risk_category: Literal["LOW", "MODERATE", "HIGH"]
    main_contributing_factors: list[dict[str, Any]]
    model_version: str
    scoring_timestamp: str


class RiskCollectionResponse(BaseModel):
    items: list[RiskRecord]
    total: int
    page: int
    page_size: int
