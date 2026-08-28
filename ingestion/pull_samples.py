# The script asks for 1,000 most recent inspection/violation rows from the NYC Open Data portal for Phase 1 exploration.

# 1,000 most recent relevant 311 records
# It keeps exactly the three complaint types identified in the plan:
# - Food Poisoning
# - Rodent
# - Food Establishment

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIRECTORY = PROJECT_ROOT / "data" / "samples"

INSPECTION_API_URL = (
    "https://data.cityofnewyork.us/resource/43nn-pn8j.json"
)

COMPLAINT_API_URL = (
    "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
)

SAMPLE_SIZE = 1_000

INSPECTION_OUTPUT_PATH = (
    SAMPLE_DIRECTORY / "dohmh_inspections_sample.json"
)

COMPLAINT_OUTPUT_PATH = (
    SAMPLE_DIRECTORY / "311_food_pest_sample.json"
)

RELEVANT_COMPLAINT_TYPES = {
    "Food Poisoning",
    "Rodent",
    "Food Establishment",
}


def build_headers() -> dict[str, str]:
    """Create request headers, adding an optional Socrata token."""

    headers = {
        "Accept": "application/json",
        "User-Agent": "SafeEatsNYC-portfolio-project",
    }

    app_token = os.getenv("NYC_OPEN_DATA_APP_TOKEN")

    if app_token:
        headers["X-App-Token"] = app_token

    return headers


def download_sample(
    url: str,
    query_parameters: dict[str, Any],
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """Request a small JSON sample from a Socrata endpoint."""

    response = requests.get(
        url,
        params=query_parameters,
        headers=headers,
        timeout=60,
    )

    response.raise_for_status()

    records = response.json()

    if not isinstance(records, list):
        raise TypeError("Expected the API response to contain a JSON list.")

    return records


def save_json(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Save records as readable UTF-8 JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        mode="w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            records,
            output_file,
            ensure_ascii=False,
            indent=2,
        )


def combined_fields(
    records: list[dict[str, Any]],
) -> set[str]:
    """Return every field found anywhere in a sample."""

    return {
        field
        for record in records
        for field in record
    }


def main() -> None:
    """Download and validate both Phase 1 samples."""

    load_dotenv()

    headers = build_headers()

    inspection_parameters = {
        "$limit": SAMPLE_SIZE,
        "$order": "inspection_date DESC, camis ASC",
    }

    complaint_parameters = {
        "$limit": SAMPLE_SIZE,
        "$where": (
            "complaint_type in "
            "('Food Poisoning', 'Rodent', 'Food Establishment')"
        ),
        "$order": "created_date DESC",
    }

    print("Downloading DOHMH inspection sample...")

    inspection_records = download_sample(
        INSPECTION_API_URL,
        inspection_parameters,
        headers,
    )

    print("Downloading filtered 311 complaint sample...")

    complaint_records = download_sample(
        COMPLAINT_API_URL,
        complaint_parameters,
        headers,
    )

    returned_complaint_types = {
        record.get("complaint_type")
        for record in complaint_records
    }

    unexpected_complaint_types = (
        returned_complaint_types - RELEVANT_COMPLAINT_TYPES
    )

    if unexpected_complaint_types:
        raise ValueError(
            "The 311 response contained unexpected complaint types: "
            f"{sorted(unexpected_complaint_types)}"
        )

    save_json(
        inspection_records,
        INSPECTION_OUTPUT_PATH,
    )

    save_json(
        complaint_records,
        COMPLAINT_OUTPUT_PATH,
    )

    print()
    print("Download complete.")
    print(
        f"Inspection rows: {len(inspection_records):,}"
    )
    print(
        f"311 complaint rows: {len(complaint_records):,}"
    )
    print(
        f"Inspection fields found: "
        f"{len(combined_fields(inspection_records))}"
    )
    print(
        f"311 fields found: "
        f"{len(combined_fields(complaint_records))}"
    )
    print(
        "311 complaint types: "
        f"{sorted(returned_complaint_types)}"
    )
    print(
        f"Saved: {INSPECTION_OUTPUT_PATH}"
    )
    print(
        f"Saved: {COMPLAINT_OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()