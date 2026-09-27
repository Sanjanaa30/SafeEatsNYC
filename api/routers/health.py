"""Health and initial AWS connectivity routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.config import Settings, get_settings
from api.dependencies import get_dependency_checker
from api.schemas.health import DependencyHealth, ServiceHealth
from api.services.health import AwsDependencyChecker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ServiceHealth)
def health(settings: Settings = Depends(get_settings)) -> ServiceHealth:
    """Report that the API process is available without contacting AWS."""

    return ServiceHealth(
        status="ok",
        service="safeeats-api",
        environment=settings.environment,
    )


@router.get("/dependencies", response_model=DependencyHealth)
def dependency_health(
    checker: AwsDependencyChecker = Depends(get_dependency_checker),
) -> DependencyHealth:
    """Verify that this backend can reach the configured S3 bucket and Athena."""

    try:
        return checker.check()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AWS data services are temporarily unavailable.",
        ) from error
