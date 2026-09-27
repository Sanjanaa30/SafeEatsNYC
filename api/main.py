"""FastAPI entry point for the SafeEats website."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers.chains import router as chains_router
from api.routers.correlation import router as correlation_router
from api.routers.health import router as health_router
from api.routers.metadata import router as metadata_router
from api.routers.overview import router as overview_router
from api.routers.restaurants import router as restaurants_router
from api.routers.risk import router as risk_router


def create_app() -> FastAPI:
    """Create and configure the API application."""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(metadata_router, prefix="/api/v1")
    application.include_router(overview_router, prefix="/api/v1")
    application.include_router(correlation_router, prefix="/api/v1")
    application.include_router(restaurants_router, prefix="/api/v1")
    application.include_router(chains_router, prefix="/api/v1")
    application.include_router(risk_router, prefix="/api/v1")
    return application


app = create_app()
