"""Profile names across the live DOHMH restaurant population.

This read-only job requests distinct CAMIS/DBA pairs, applies the same rules
used for the brand reference, and writes a review queue. It does not mutate
the alias or co-brand decisions automatically.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from name_normalization import (
    brand_candidates,
    canonicalize_name,
    load_name_references,
    normalize_name,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIRECTORY = PROJECT_ROOT / "data" / "reference"
REPORT_PATH = (
    PROJECT_ROOT / "docs" / "project_documents" / "restaurant_name_profile.md"
)
REVIEW_PATH = PROJECT_ROOT / "docs" / "co_brand_review_queue.csv"
ALIAS_REVIEW_PATH = PROJECT_ROOT / "docs" / "brand_alias_review_queue.csv"
DOHMH_API_URL = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"
PAGE_SIZE = 50_000

# fetch_restaurant_names(): Connects to the live NYC Open Data API (DOHMH_API_URL) and pulls every single unique restaurant ID (camis) and business name (dba) combination.
# Pagination (PAGE_SIZE = 50_000): Because there are tens of thousands of restaurants in New York City, the script downloads them in batches of 50,000 rows at a time in a loop until it has grabbed everything safely.
def fetch_restaurant_names() -> list[dict[str, Any]]:
    """Fetch every distinct CAMIS/DBA pair with stable pagination."""

    records: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = requests.get(
            DOHMH_API_URL,
            params={
                "$select": "camis,dba",
                "$where": "dba is not null",
                "$group": "camis,dba",
                "$order": "camis,dba",
                "$limit": PAGE_SIZE,
                "$offset": offset,
            },
            timeout=120,
        )
        response.raise_for_status()
        page = response.json()
        records.extend(page)

        if len(page) < PAGE_SIZE:
            return records
        offset += PAGE_SIZE

# contained_brand_matches(): This smart function looks at a restaurant's full name and checks if any known fast-food or corporate brand name is hidden inside it (e.g., if a place is called "JFK SUBWAY EXPRESS", it spots "SUBWAY"). 
# It also prevents shorter, nested names from causing false alarms.
def contains_whole_brand(text: str, brand: str) -> bool:
    """Return True when a complete brand name appears in the text."""

    pattern = rf"(?:^| ){re.escape(brand)}(?: |$)"
    return re.search(pattern, text) is not None


def contained_brand_matches(
    normalized_name: str,
    known_brands: set[str],
) -> tuple[str, ...]:
    """Find distinct known brands while suppressing nested shorter names."""

    matches = {
        brand
        for brand in known_brands
        if contains_whole_brand(normalized_name, brand)
    }

    # If "SHAHS HALAL FOOD" matches, do not also return "SHAHS HALAL".
    longest_matches = [
        brand
        for brand in matches
        if not any(
            brand != other and contains_whole_brand(other, brand)
            for other in matches
        )
    ]
    return tuple(sorted(longest_matches))


def build_restaurant_table(
    records: list[dict[str, Any]],
    aliases: dict[str, str],
    co_brands: dict[str, tuple[str, ...]],
    fast_food_brands: set[str],
) -> pd.DataFrame:
    """Add normalized names and simple brand flags to the API records."""

    known_brands = fast_food_brands | {
        brand for brands in co_brands.values() for brand in brands
    }
    restaurants = pd.DataFrame(records)
    restaurants["name_syntax_normalized"] = restaurants["dba"].map(
        normalize_name
    )
    restaurants["name_normalized"] = restaurants["dba"].map(
        lambda name: canonicalize_name(name, aliases)
    )
    restaurants["brand_candidates"] = restaurants["dba"].map(
        lambda name: brand_candidates(name, aliases, co_brands)
    )
    restaurants["detected_known_brands"] = restaurants[
        "name_syntax_normalized"
    ].map(lambda name: contained_brand_matches(name, known_brands))
    restaurants["is_reviewed_co_brand"] = restaurants[
        "name_syntax_normalized"
    ].isin(co_brands)
    restaurants["has_separator"] = restaurants["dba"].str.contains(
        r"[/&,]|\bAND\b",
        case=False,
        regex=True,
        na=False,
    )
    restaurants["is_confirmed_fast_food"] = restaurants[
        "brand_candidates"
    ].map(lambda values: bool(set(values) & fast_food_brands))
    return restaurants


def build_co_brand_review(restaurants: pd.DataFrame) -> pd.DataFrame:
    """Create the co-brand review queue."""

    needs_review = (
        restaurants["has_separator"]
        | restaurants["detected_known_brands"].map(len).gt(1)
        | restaurants["is_reviewed_co_brand"]
    )
    review = restaurants.loc[needs_review].copy()
    review["detected_known_brands"] = review[
        "detected_known_brands"
    ].map(lambda values: " | ".join(values))
    review["brand_candidates"] = review["brand_candidates"].map(
        lambda values: " | ".join(values)
    )

    group_columns = [
        "dba",
        "name_syntax_normalized",
        "name_normalized",
        "detected_known_brands",
        "brand_candidates",
        "is_reviewed_co_brand",
        "has_separator",
    ]
    return (
        review.groupby(group_columns, as_index=False)["camis"]
        .nunique()
        .rename(columns={"camis": "location_count"})
        .sort_values(["is_reviewed_co_brand", "dba"], ascending=[False, True])
    )


def build_alias_review(restaurants: pd.DataFrame) -> pd.DataFrame:
    """Create the alias review queue."""

    needs_review = (
        restaurants["detected_known_brands"].map(len).eq(1)
        & ~restaurants["is_confirmed_fast_food"]
        & ~restaurants["is_reviewed_co_brand"]
        & ~restaurants["has_separator"]
    )
    review = restaurants.loc[needs_review].copy()
    review["detected_brand"] = review["detected_known_brands"].str[0]

    group_columns = [
        "dba",
        "name_syntax_normalized",
        "name_normalized",
        "detected_brand",
    ]
    return (
        review.groupby(group_columns, as_index=False)["camis"]
        .nunique()
        .rename(columns={"camis": "location_count"})
        .sort_values(["location_count", "dba"], ascending=[False, True])
    )


def build_report(
    restaurants: pd.DataFrame,
    co_brand_review: pd.DataFrame,
    alias_review: pd.DataFrame,
) -> str:
    """Create the Markdown summary shown in the docs folder."""

    likely_co_brands = co_brand_review[
        co_brand_review["detected_known_brands"].str.contains(r"\|", regex=True)
    ]
    reviewed = co_brand_review[co_brand_review["is_reviewed_co_brand"]]

    return "\n".join(
        [
            "# Full Restaurant Name Profile",
            "",
            "This report uses distinct CAMIS/DBA pairs from the live NYC DOHMH ",
            "Restaurant Inspection Results endpoint. Results reflect the source ",
            "at execution time; the review queue never changes policy automatically.",
            "",
            f"- Distinct CAMIS/DBA pairs: {len(restaurants):,}",
            f"- Distinct CAMIS values: {restaurants['camis'].nunique():,}",
            f"- Distinct source DBA values: {restaurants['dba'].nunique():,}",
            f"- Distinct canonical names: {restaurants['name_normalized'].nunique():,}",
            f"- Confirmed fast-food CAMIS values: "
            f"{restaurants.loc[restaurants['is_confirmed_fast_food'], 'camis'].nunique():,}",
            f"- Reviewed co-brand CAMIS values: "
            f"{restaurants.loc[restaurants['is_reviewed_co_brand'], 'camis'].nunique():,}",
            f"- Review-queue names: {co_brand_review['dba'].nunique():,}",
            f"- Names containing multiple known brands: {len(likely_co_brands):,}",
            f"- Remaining possible alias names requiring review: {len(alias_review):,}",
            "",
            "## Reviewed co-brands present",
            "",
            "```",
            reviewed[["dba", "brand_candidates", "location_count"]].to_string(
                index=False
            ),
            "```",
            "",
            "## Multiple-known-brand candidates",
            "",
            "```",
            likely_co_brands[
                ["dba", "detected_known_brands", "location_count"]
            ].to_string(index=False),
            "```",
            "",
            f"Full review queue: `{REVIEW_PATH.relative_to(PROJECT_ROOT)}`",
            f"Alias review queue: `{ALIAS_REVIEW_PATH.relative_to(PROJECT_ROOT)}`",
            "",
        ]
    )

# The Master Execution (main())
# This is where all the data processing and report generation happen:
# Loading References: Loads your alias rules, co-brand lists, and known fast-food brands.
# Analyzing the Live Population: Converts the downloaded city records into a Pandas table and runs every single restaurant name through your normalization and brand-detection rules.
# Building the Review Queues:
# REVIEW_PATH (co_brand_review_queue.csv): Flags names that contain separators (like &, AND, or /), have multiple known brands smashed together, or are already recognized co-brands, counting how many locations share that name.
# ALIAS_REVIEW_PATH (brand_alias_review_queue.csv): Captures names that contain a known brand but aren't yet officially classified as fast-food, giving you a clean list to review and potentially add to your alias or override lists later.
# Generating the Markdown Report (restaurant_name_profile.md): Compiles statistics (like total unique restaurants, confirmed fast-food counts, and review-queue sizes) and writes a summary report.
def main() -> None:
    """Build the live name profile and non-destructive review queue."""

    aliases, co_brands, fast_food_brands = load_name_references(
        REFERENCE_DIRECTORY
    )
    records = fetch_restaurant_names()
    restaurants = build_restaurant_table(
        records,
        aliases,
        co_brands,
        fast_food_brands,
    )
    co_brand_review = build_co_brand_review(restaurants)
    alias_review = build_alias_review(restaurants)

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    co_brand_review.to_csv(REVIEW_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    alias_review.to_csv(
        ALIAS_REVIEW_PATH,
        index=False,
        quoting=csv.QUOTE_MINIMAL,
    )
    report = build_report(restaurants, co_brand_review, alias_review)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Profiled {len(restaurants):,} distinct CAMIS/DBA pairs.")
    print(f"Report: {REPORT_PATH}")
    print(f"Review queue: {REVIEW_PATH}")
    print(f"Alias review queue: {ALIAS_REVIEW_PATH}")


if __name__ == "__main__":
    main()
