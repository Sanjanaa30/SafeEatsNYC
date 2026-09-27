"""Environment settings used only by the FastAPI backend."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load API, Athena, and S3 settings from the environment."""

    app_name: str = "SafeEats NYC API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    aws_profile: str | None = "safeeats-dev"
    aws_region: str = "us-east-1"
    safeeats_s3_bucket: str
    athena_workgroup: str = "primary"
    athena_dbt_schema: str = "safeeats_gold"
    athena_output_location: str | None = None
    athena_query_timeout_seconds: int = 90
    api_cache_ttl_seconds: int = 300
    risk_score_run_id: str = "current-risk-scores-20260906-v1"
    risk_score_pointer_key: str = "ml/current_scores/latest.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

    @property
    def query_output_location(self) -> str:
        """Return the configured Athena result folder or a safe bucket default."""

        if self.athena_output_location:
            return self.athena_output_location
        return f"s3://{self.safeeats_s3_bucket}/athena/api-query-results/"

    @property
    def risk_score_key(self) -> str:
        """Return the explicitly approved Phase 5 score artifact."""

        return (
            "ml/current_scores/"
            f"run_id={self.risk_score_run_id}/"
            "current_restaurant_risk_scores.parquet"
        )

    @property
    def risk_scoring_report_key(self) -> str:
        return f"ml/current_scores/run_id={self.risk_score_run_id}/scoring_report.json"


@lru_cache
def get_settings() -> Settings:
    """Create one settings object for the API process."""

    return Settings()  # type: ignore[call-arg]
