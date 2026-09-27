"""NYC Open Data source definitions used by the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceConfig:
    """Configuration and validation contract for one API source."""

    name: str
    api_url: str
    timestamp_field: str
    required_fields: frozenset[str]
    order_fields: tuple[str, ...]
    bronze_directory: str
    base_where: str | None = None
    allowed_complaint_types: frozenset[str] | None = None


DOHMH_INSPECTIONS = SourceConfig(
    name="dohmh_inspections",
    api_url="https://data.cityofnewyork.us/resource/43nn-pn8j.json",
    timestamp_field="inspection_date",
    required_fields=frozenset({"camis", "inspection_date"}),
    order_fields=(
        "inspection_date",
        "camis",
        "violation_code",
    ),
    bronze_directory="inspections",
)

RELEVANT_311_TYPE_NAMES = (
    "Food Poisoning",
    "Rodent",
    "Food Establishment",
)
RELEVANT_311_TYPES = frozenset(RELEVANT_311_TYPE_NAMES)
RELEVANT_311_WHERE = (
    "complaint_type in ("
    + ", ".join(f"'{name}'" for name in RELEVANT_311_TYPE_NAMES)
    + ")"
)

COMPLAINTS_311 = SourceConfig(
    name="complaints_311",
    api_url="https://data.cityofnewyork.us/resource/erm2-nwe9.json",
    timestamp_field="created_date",
    required_fields=frozenset(
        {
            "unique_key",
            "created_date",
            "complaint_type",
        }
    ),
    order_fields=("created_date", "unique_key"),
    bronze_directory="complaints_311",
    base_where=RELEVANT_311_WHERE,
    allowed_complaint_types=RELEVANT_311_TYPES,
)
