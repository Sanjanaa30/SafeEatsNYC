"""Load and validate the explicitly approved Phase 5 risk-score artifact."""

import io
import json
from datetime import date, datetime
from threading import Lock
from typing import Any

from botocore.exceptions import ClientError

from api.config import Settings
from api.services.cache import TtlCache


class RiskScoreError(RuntimeError):
    """Raised when an approved risk artifact is absent or malformed."""


class RiskScoreService:
    """Read current risk scores from S3 and cache the result in memory."""

    def __init__(self, s3_client: Any, settings: Settings) -> None:
        self.s3 = s3_client
        self.settings = settings
        self.cache = TtlCache[list[dict[str, Any]]](settings.api_cache_ttl_seconds)
        self.summary_cache = TtlCache[dict[str, Any]](settings.api_cache_ttl_seconds)
        self.pointer_cache = TtlCache[dict[str, str]](settings.api_cache_ttl_seconds)
        self._load_lock = Lock()

    def summary(self) -> dict[str, Any]:
        """Read the tiny score manifest without loading the Parquet dataset."""

        artifact = self.active_artifact()
        report_key = artifact["scoring_report_key"]
        cached = self.summary_cache.get(report_key)
        if cached is not None:
            return cached
        response = self.s3.get_object(
            Bucket=self.settings.safeeats_s3_bucket,
            Key=report_key,
        )
        try:
            report = json.loads(response["Body"].read())
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RiskScoreError("The risk scoring report is malformed.") from error
        required = {"model_version", "scoring_timestamp", "score_run_id"}
        if required - report.keys():
            raise RiskScoreError("The risk scoring report is incomplete.")
        if report["score_run_id"] != artifact["score_run_id"]:
            raise RiskScoreError("The risk pointer and scoring report disagree.")
        self.summary_cache.set(report_key, report)
        return report

    def active_artifact(self) -> dict[str, str]:
        """Resolve the promoted score artifact, with the explicit run as fallback."""

        cached = self.pointer_cache.get(self.settings.risk_score_pointer_key)
        if cached is not None:
            return cached
        try:
            response = self.s3.get_object(
                Bucket=self.settings.safeeats_s3_bucket,
                Key=self.settings.risk_score_pointer_key,
            )
            pointer = json.loads(response["Body"].read())
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {
                "404",
                "NoSuchKey",
                "NoSuchObject",
            }:
                raise
            pointer = self._fallback_artifact()
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RiskScoreError(
                "The latest risk-score pointer is malformed."
            ) from error

        required = {"score_run_id", "score_key", "scoring_report_key"}
        if required - pointer.keys():
            raise RiskScoreError("The latest risk-score pointer is incomplete.")
        run_id = str(pointer["score_run_id"])
        expected_prefix = f"ml/current_scores/run_id={run_id}/"
        if not str(pointer["score_key"]).startswith(expected_prefix) or not str(
            pointer["scoring_report_key"]
        ).startswith(expected_prefix):
            raise RiskScoreError("The latest risk-score pointer has unsafe paths.")
        artifact = {key: str(pointer[key]) for key in required}
        self.pointer_cache.set(self.settings.risk_score_pointer_key, artifact)
        return artifact

    def _fallback_artifact(self) -> dict[str, str]:
        return {
            "score_run_id": self.settings.risk_score_run_id,
            "score_key": self.settings.risk_score_key,
            "scoring_report_key": self.settings.risk_scoring_report_key,
        }

    def load(self) -> list[dict[str, Any]]:
        score_key = self.active_artifact()["score_key"]
        cached = self.cache.get(score_key)
        if cached is not None:
            return cached

        with self._load_lock:
            cached = self.cache.get(score_key)
            if cached is not None:
                return cached
            return self._load_from_s3(score_key)

    def _load_from_s3(self, score_key: str) -> list[dict[str, Any]]:
        """Perform one protected S3 download and Parquet conversion."""

        response = self.s3.get_object(
            Bucket=self.settings.safeeats_s3_bucket,
            Key=score_key,
        )
        import pyarrow.parquet as parquet

        table = parquet.read_table(io.BytesIO(response["Body"].read()))
        rows = [self._normalize(row) for row in table.to_pylist()]
        self.cache.set(score_key, rows)
        return rows

    def by_restaurant_key(self) -> dict[str, dict[str, Any]]:
        return {row["restaurant_key"]: row for row in self.load()}

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        required = {
            "restaurant_key",
            "risk_probability",
            "risk_category",
            "main_contributing_factors",
            "model_version",
            "scoring_timestamp",
        }
        if required - row.keys():
            raise RiskScoreError("The approved risk-score file is incomplete.")

        probability = float(row["risk_probability"])
        category = str(row["risk_category"]).upper()
        if not 0 <= probability <= 1 or category not in {
            "LOW",
            "MODERATE",
            "HIGH",
        }:
            raise RiskScoreError("The approved risk-score file has invalid values.")

        factors = row.get("main_contributing_factors")
        if isinstance(factors, str):
            try:
                factors = json.loads(factors)
            except json.JSONDecodeError as error:
                raise RiskScoreError("Risk factors are malformed.") from error
        if not isinstance(factors, list):
            raise RiskScoreError("Risk factors are malformed.")

        normalized = dict(row)
        normalized["risk_probability"] = probability
        normalized["risk_category"] = category
        normalized["main_contributing_factors"] = factors
        for key, value in normalized.items():
            if isinstance(value, (date, datetime)):
                normalized[key] = value.isoformat()
        return normalized
