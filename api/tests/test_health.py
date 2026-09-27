"""Tests for the Phase 7 setup endpoints."""

from fastapi.testclient import TestClient

from api.dependencies import get_dependency_checker
from api.main import app
from api.schemas.health import DependencyHealth


class SuccessfulChecker:
    def check(self) -> DependencyHealth:
        return DependencyHealth(status="ok", s3="reachable", athena="reachable")


class FailingChecker:
    def check(self) -> DependencyHealth:
        raise RuntimeError("temporary AWS failure")


client = TestClient(app)


def test_api_health_does_not_expose_aws_configuration():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "safeeats-api",
        "environment": "development",
    }
    assert "bucket" not in response.text.lower()
    assert "credential" not in response.text.lower()


def test_dependency_health_reports_backend_connections():
    app.dependency_overrides[get_dependency_checker] = SuccessfulChecker
    try:
        response = client.get("/api/v1/health/dependencies")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "s3": "reachable",
        "athena": "reachable",
    }


def test_dependency_failure_returns_safe_message():
    app.dependency_overrides[get_dependency_checker] = FailingChecker
    try:
        response = client.get("/api/v1/health/dependencies")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "AWS data services are temporarily unavailable."
    }
    assert "temporary AWS failure" not in response.text
