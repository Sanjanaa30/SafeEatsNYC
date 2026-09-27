"""Build geographic and brand reference files used by SafeEatsNYC.

This manual job does not write to the Bronze or Silver layers.
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
from name_normalization import (
    apply_brand_classification_overrides,
    canonicalize_name,
    load_aliases,
    load_brand_classification_overrides,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIRECTORY = PROJECT_ROOT / "data" / "reference"

BOROUGH_OUTPUT_PATH = REFERENCE_DIRECTORY / "nyc_borough_boundaries.geojson"
ZCTA_OUTPUT_PATH = REFERENCE_DIRECTORY / "nyc_zcta_boundaries.geojson"
ZIP_TO_NTA_OUTPUT_PATH = REFERENCE_DIRECTORY / "zip_to_nta.csv"
FAST_FOOD_OUTPUT_PATH = REFERENCE_DIRECTORY / "fast_food_brands.csv"

# Official NYC Open Data GeoJSON exports.
BOROUGH_GEOJSON_URL = (
    "https://data.cityofnewyork.us/api/v3/views/"
    "gthc-hcne/query.geojson?accessType=DOWNLOAD"
)

ZCTA_GEOJSON_URL = (
    "https://data.cityofnewyork.us/api/v3/views/"
    "35j5-n34v/query.geojson?accessType=DOWNLOAD"
)

NTA_GEOJSON_URL = (
    "https://data.cityofnewyork.us/api/v3/views/"
    "9nt8-h7nd/query.geojson?accessType=DOWNLOAD"
)

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Approximate NYC bounds: south, west, north, east.
NYC_BOUNDING_BOX = (
    40.4774,
    -74.2591,
    40.9176,
    -73.7004,
)

HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "SafeEatsNYC-portfolio-project",
}


def download_file(url: str, output_path: Path) -> None:
    """Download a file without changing its contents."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(
        url,
        headers=HTTP_HEADERS,
        timeout=180,
        stream=True,
    ) as response:
        response.raise_for_status()

        with output_path.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)


def load_geojson(path: Path) -> dict[str, Any]:
    """Load and validate a GeoJSON FeatureCollection."""

    with path.open(mode="r", encoding="utf-8") as input_file:
        document = json.load(input_file)

    if document.get("type") != "FeatureCollection":
        raise ValueError(f"{path.name} is not a GeoJSON FeatureCollection.")

    features = document.get("features")

    if not isinstance(features, list):
        raise ValueError(f"{path.name} does not contain a feature list.")

    return document


def normalize_column_names(dataframe: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Make geographic source columns lowercase."""

    renamed_columns = {column: str(column).lower() for column in dataframe.columns}
    return dataframe.rename(columns=renamed_columns)


def ensure_source_crs(dataframe: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Ensure GeoJSON data is treated as WGS 84."""

    if dataframe.crs is None:
        return dataframe.set_crs(epsg=4326)

    return dataframe


def build_zip_to_nta_lookup(zcta_path: Path, nta_path: Path) -> int:
    """Assign each ZCTA to its largest-overlapping NTA."""

    zcta = normalize_column_names(gpd.read_file(zcta_path))
    nta = normalize_column_names(gpd.read_file(nta_path))

    zcta = ensure_source_crs(zcta)
    nta = ensure_source_crs(nta)

    required_zcta_columns = {"zcta5", "geometry"}
    required_nta_columns = {"nta2020", "ntaname", "boroname", "geometry"}
    missing_zcta_columns = required_zcta_columns - set(zcta.columns)
    missing_nta_columns = required_nta_columns - set(nta.columns)

    if missing_zcta_columns:
        raise ValueError(f"ZCTA data is missing fields: {sorted(missing_zcta_columns)}")

    if missing_nta_columns:
        raise ValueError(f"NTA data is missing fields: {sorted(missing_nta_columns)}")

    # EPSG:2263 is New York State Plane, Long Island.
    # It lets us compare polygon areas using a projected CRS.
    zcta_projected = zcta[["zcta5", "geometry"]].to_crs(epsg=2263)
    nta_projected = nta[["nta2020", "ntaname", "boroname", "geometry"]].to_crs(
        epsg=2263
    )

    intersections = gpd.overlay(
        zcta_projected,
        nta_projected,
        how="intersection",
        keep_geom_type=False,
    )

    intersections["overlap_area"] = intersections.geometry.area

    dominant_matches = (
        intersections.sort_values(by=["zcta5", "overlap_area"], ascending=[True, False])
        .drop_duplicates(subset=["zcta5"], keep="first")
        .rename(
            columns={
                "zcta5": "zip",
                "nta2020": "nta_code",
                "ntaname": "nta_name",
                "boroname": "borough",
            }
        )
    )

    lookup = dominant_matches[["zip", "nta_code", "nta_name", "borough"]].copy()
    lookup["zip"] = lookup["zip"].astype(str).str.zfill(5)
    lookup = lookup.sort_values(by="zip")

    if lookup["zip"].duplicated().any():
        raise ValueError("ZIP-to-NTA lookup contains duplicate ZIP rows.")

    if len(lookup) < 200:
        raise ValueError("ZIP-to-NTA lookup contains fewer rows than expected.")

    lookup.to_csv(ZIP_TO_NTA_OUTPUT_PATH, index=False, encoding="utf-8")

    return len(lookup)


BRAND_ALIAS_PATH = REFERENCE_DIRECTORY / "brand_aliases.csv"
BRAND_CLASSIFICATION_OVERRIDE_PATH = (
    REFERENCE_DIRECTORY / "brand_classification_overrides.csv"
)
BRAND_ALIASES = load_aliases(BRAND_ALIAS_PATH)
BRAND_CLASSIFICATION_OVERRIDES = load_brand_classification_overrides(
    BRAND_CLASSIFICATION_OVERRIDE_PATH
)


def download_fast_food_brands() -> int:
    """Download NYC fast-food brand tags from OpenStreetMap."""

    south, west, north, east = NYC_BOUNDING_BOX

    overpass_query = f"""
    [out:json][timeout:180];
    (
      nwr
        ["amenity"="fast_food"]
        ["brand"]
        ({south},{west},{north},{east});
    );
    out tags;
    """

    response = requests.post(
        OVERPASS_API_URL,
        data={"data": overpass_query},
        headers=HTTP_HEADERS,
        timeout=240,
    )
    response.raise_for_status()
    payload = response.json()
    elements = payload.get("elements", [])

    normalized_brands: set[str] = set()

    for element in elements:
        tags = element.get("tags", {})
        raw_brand = tags.get("brand")

        if not raw_brand:
            continue

        # OSM sometimes stores multiple tag values separated
        # with a semicolon.
        for individual_brand in raw_brand.split(";"):
            normalized = canonicalize_name(individual_brand, BRAND_ALIASES)

            if normalized:
                normalized_brands.add(normalized)

    normalized_brands = apply_brand_classification_overrides(
        normalized_brands,
        BRAND_CLASSIFICATION_OVERRIDES,
    )

    if not normalized_brands:
        raise ValueError("No NYC fast-food brands were returned.")

    with FAST_FOOD_OUTPUT_PATH.open(
        mode="w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["brand_name_normalized"])

        writer.writeheader()

        for brand in sorted(normalized_brands):
            writer.writerow({"brand_name_normalized": brand})

    return len(normalized_brands)


def main() -> None:
    """Download and validate every static reference source."""

    REFERENCE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("Downloading NYC borough boundaries...")

    download_file(BOROUGH_GEOJSON_URL, BOROUGH_OUTPUT_PATH)
    borough_document = load_geojson(BOROUGH_OUTPUT_PATH)
    borough_count = len(borough_document["features"])

    if borough_count != 5:
        raise ValueError(
            f"Expected exactly five NYC borough features, but received {borough_count}."
        )

    print(f"Borough features: {borough_count}")

    print("Downloading NYC ZCTA boundaries...")

    download_file(ZCTA_GEOJSON_URL, ZCTA_OUTPUT_PATH)
    zcta_document = load_geojson(ZCTA_OUTPUT_PATH)
    zcta_count = len(zcta_document["features"])

    if zcta_count < 200:
        raise ValueError("The ZCTA dataset contains fewer features than expected.")

    print(f"ZCTA features: {zcta_count}")

    print("Downloading NTA boundaries temporarily...")

    with tempfile.TemporaryDirectory() as temporary_directory:
        nta_temporary_path = Path(temporary_directory) / "nyc_nta_boundaries.geojson"

        download_file(NTA_GEOJSON_URL, nta_temporary_path)
        load_geojson(nta_temporary_path)

        print("Building dominant ZIP-to-NTA lookup...")

        lookup_count = build_zip_to_nta_lookup(ZCTA_OUTPUT_PATH, nta_temporary_path)

    print(f"ZIP-to-NTA rows: {lookup_count}")

    print("Downloading OpenStreetMap fast-food brands...")

    brand_count = download_fast_food_brands()

    print(f"Unique normalized brands: {brand_count}")

    print()
    print("Reference-data preparation complete.")
    print(f"Saved: {BOROUGH_OUTPUT_PATH}")
    print(f"Saved: {ZCTA_OUTPUT_PATH}")
    print(f"Saved: {ZIP_TO_NTA_OUTPUT_PATH}")
    print(f"Saved: {FAST_FOOD_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
