"""Shared FastAPI dependencies."""

from functools import lru_cache

import boto3
from botocore.config import Config

from api.config import get_settings
from api.services.athena import AthenaQueryService
from api.services.chains import ChainService
from api.services.correlation import CorrelationService
from api.services.health import AwsDependencyChecker
from api.services.metadata import MetadataService
from api.services.overview import OverviewService
from api.services.restaurants import RestaurantService
from api.services.risk import RiskScoreService

AWS_CLIENT_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "standard"},
)


@lru_cache
def get_aws_session() -> boto3.Session:
    """Create the backend AWS session without exposing it to the browser."""

    settings = get_settings()
    return boto3.Session(
        profile_name=settings.aws_profile or None,
        region_name=settings.aws_region,
    )


@lru_cache
def get_dependency_checker() -> AwsDependencyChecker:
    """Create the small S3 and Athena connectivity checker."""

    return AwsDependencyChecker(get_aws_session(), get_settings())


@lru_cache
def get_athena_service() -> AthenaQueryService:
    """Create one cached Athena query service for the API process."""

    settings = get_settings()
    client = get_aws_session().client(
        "athena", region_name=settings.aws_region, config=AWS_CLIENT_CONFIG
    )
    return AthenaQueryService(client, settings)


@lru_cache
def get_risk_score_service() -> RiskScoreService:
    """Create one cached reader for the approved current score file."""

    settings = get_settings()
    client = get_aws_session().client(
        "s3", region_name=settings.aws_region, config=AWS_CLIENT_CONFIG
    )
    return RiskScoreService(client, settings)


@lru_cache
def get_overview_service() -> OverviewService:
    return OverviewService(get_athena_service())


@lru_cache
def get_correlation_service() -> CorrelationService:
    return CorrelationService(get_athena_service())


@lru_cache
def get_restaurant_service() -> RestaurantService:
    return RestaurantService(get_athena_service())


@lru_cache
def get_chain_service() -> ChainService:
    return ChainService(get_athena_service())


@lru_cache
def get_metadata_service() -> MetadataService:
    return MetadataService(
        get_athena_service(), get_risk_score_service(), get_settings()
    )
