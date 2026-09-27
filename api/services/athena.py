"""Reusable, bounded Athena query execution for dashboard endpoints."""

import logging
import time
from datetime import date, datetime
from typing import Any

from api.config import Settings
from api.services.cache import TtlCache

LOGGER = logging.getLogger(__name__)


class AthenaQueryError(RuntimeError):
    """Raised when Athena fails or cancels a query."""


class AthenaQueryTimeout(TimeoutError):
    """Raised after a bounded query wait expires."""


class AthenaQueryService:
    """Execute Athena SQL and return typed rows without leaking AWS details."""

    def __init__(self, client: Any, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.cache = TtlCache[list[dict[str, Any]]](settings.api_cache_ttl_seconds)

    def query(
        self,
        sql: str,
        *,
        cache_key: str | None = None,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        """Execute one SQL statement with polling, pagination, and conversion."""

        key = cache_key or sql
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        started_at = time.monotonic()
        response = self.client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": self.settings.athena_dbt_schema},
            WorkGroup=self.settings.athena_workgroup,
            ResultConfiguration={
                "OutputLocation": self.settings.query_output_location,
            },
        )
        execution_id = response["QueryExecutionId"]
        timeout = timeout_seconds or self.settings.athena_query_timeout_seconds
        deadline = started_at + timeout

        while time.monotonic() < deadline:
            execution = self.client.get_query_execution(QueryExecutionId=execution_id)[
                "QueryExecution"
            ]
            state = execution["Status"]["State"]
            if state == "SUCCEEDED":
                rows = self._read_results(execution_id, deadline)
                self.cache.set(key, rows)
                LOGGER.info(
                    "Athena query succeeded execution_id=%s rows=%s duration_seconds=%.3f",
                    execution_id,
                    len(rows),
                    time.monotonic() - started_at,
                )
                return rows
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["Status"].get("StateChangeReason", state)
                LOGGER.error(
                    "Athena query failed execution_id=%s state=%s reason=%s",
                    execution_id,
                    state,
                    reason,
                )
                raise AthenaQueryError(f"Athena query ended in state {state}.")
            time.sleep(0.25)

        self.client.stop_query_execution(QueryExecutionId=execution_id)
        LOGGER.error("Athena query timed out execution_id=%s", execution_id)
        raise AthenaQueryTimeout(f"Athena query exceeded {timeout} seconds.")

    def _read_results(self, execution_id: str, deadline: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        token: str | None = None
        first_page = True
        columns: list[dict[str, Any]] = []

        while True:
            if time.monotonic() >= deadline:
                raise AthenaQueryTimeout(
                    "Athena result pagination exceeded the query timeout."
                )
            arguments: dict[str, Any] = {
                "QueryExecutionId": execution_id,
                "MaxResults": 1000,
            }
            if token:
                arguments["NextToken"] = token
            page = self.client.get_query_results(**arguments)
            if first_page:
                columns = page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            page_rows = page["ResultSet"].get("Rows", [])
            if first_page and page_rows:
                page_rows = page_rows[1:]
            for raw_row in page_rows:
                values = raw_row.get("Data", [])
                rows.append(
                    {
                        column["Name"]: self._convert(
                            values[index].get("VarCharValue")
                            if index < len(values)
                            else None,
                            column["Type"],
                        )
                        for index, column in enumerate(columns)
                    }
                )
            token = page.get("NextToken")
            first_page = False
            if not token:
                return rows

    @staticmethod
    def _convert(value: str | None, athena_type: str) -> Any:
        if value is None:
            return None
        normalized = athena_type.lower()
        if normalized in {"tinyint", "smallint", "integer", "bigint"}:
            return int(value)
        if normalized in {"real", "float", "double"} or normalized.startswith(
            "decimal"
        ):
            return float(value)
        if normalized == "boolean":
            return value.lower() == "true"
        if normalized == "date":
            return date.fromisoformat(value).isoformat()
        if normalized.startswith("timestamp"):
            timestamp = value.replace(" UTC", "+00:00")
            return datetime.fromisoformat(timestamp).isoformat()
        if normalized.startswith("array"):
            return _parse_athena_array(value)
        return value


def _parse_athena_array(value: str) -> list[str]:
    """Parse Athena's printable array form used by Gold chain tables."""

    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text:
        return []
    return [item.strip().strip('"') for item in text.split(",")]
