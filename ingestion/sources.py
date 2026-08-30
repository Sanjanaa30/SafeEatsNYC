"""
This script acts as a blueprint or rulebook for downloading data from NYC Open Data. 
Instead of writing separate code for every dataset, it creates a standardized configuration template (SourceConfig) to define 
how both the health inspections (DOHMH) and 311 complaints (311) should be handled.

"""

from __future__ import annotations

from dataclasses import dataclass

# Creates a strict, immutable container (meaning it can't accidentally be modified once created) 
# that holds all the rules needed to ingest a specific data source.
@dataclass(frozen=True)
class SourceConfig:
    """Configuration and validation contract for one API source."""
    name: str # The identifier for the data source.
    api_url: str # The URL of the API endpoint for the data source.
    timestamp_field: str # The date column used for tracking when things happened (e.g., inspection date or complaint creation date).
    required_fields: frozenset[str] # The set of fields that are required for the data source.
    order_fields: tuple[str, ...] # The order in which the fields should be processed.
    bronze_directory: str # The local folder name where raw downloaded files are saved.
    base_where: str | None = None # An optional SQL WHERE clause to filter the data at the API level.
    allowed_complaint_types: frozenset[str] | None = None # A set of complaint types that are allowed for this source, if applicable.

# Sets up the configuration for restaurant inspections using the 43nn-pn8j endpoint. 
# It requires fields like camis and inspection_date to be present and sorts them by date, restaurant ID, and violation code.
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

# Defines the relevant 311 complaint types that are of interest for this pipeline.
RELEVANT_311_TYPE_NAMES = (
    "Food Poisoning",
    "Rodent",
    "Food Establishment",
)
RELEVANT_311_TYPES = frozenset(RELEVANT_311_TYPE_NAMES)
RELEVANT_311_WHERE = "complaint_type in (" + ", ".join(
    f"'{name}'" for name in RELEVANT_311_TYPE_NAMES
) + ")"

# It restricts downloads only to specific complaint types: "Food Poisoning", "Rodent", and "Food Establishment", ensuring your data stays clean and focused on restaurant safety.
# RELEVANT_311_TYPES & COMPLAINTS_311 (Configuring 311 Complaints)
# Sets up the configuration for 311 complaints using the erm2-nwe9 endpoint.
# It restricts downloads only to specific complaint types: "Food Poisoning", "Rodent", and "Food Establishment", ensuring your data stays clean and focused on restaurant safety.
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
