"""
Shared restaurant and brand name normalization rules.

The CSV files hold reviewed business decisions; punctuation alone is never
treated as proof that a restaurant is co-branded.

This script acts as the cleaning engine for restaurant names and brand names in your project. 
It makes sure that messy, differently spelled names (like "McDonald's LLC", "MCD", or "mcdonalds ") are all cleaned up and matched correctly.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

# A rule that looks for corporate endings at the very end of a restaurant name—like LLC, INC, CORP, or LTD—and strips them off so they don't clutter the actual brand name.

LEGAL_SUFFIX_PATTERN = re.compile(
    r"(?:\s*,?\s*\b(?:"
    r"LLC|INC|INCORPORATED|CORP|CORPORATION|LTD|LIMITED"
    r")\b\.?)+\s*$"
)

# _require_columns(): A safety check. When the script opens your CSV reference files, it checks to make sure the required column headers (like alias_name_normalized) actually exist. 
# If a column is missing, it crashes safely with a clear error message.

def _require_columns(
    fieldnames: list[str] | None,
    required: set[str],
    path: Path,
) -> None:
    """Fail clearly when a reviewed reference file has the wrong schema."""

    missing = required - set(fieldnames or [])
    if missing:
        raise ValueError(
            f"{path.name} is missing columns: {sorted(missing)}"
        )


def _read_reference_rows(
    path: Path,
    required_columns: set[str],
) -> list[dict[str, str]]:
    """Read one reference CSV and validate its column names once."""

    with path.open(mode="r", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        _require_columns(reader.fieldnames, required_columns, path)
        return list(reader)

# normalize_name(name): This is the heavy lifter. It takes any raw restaurant name and turns it into clean, uniform text by doing the following:
# Converts everything to uppercase.
# Strips out accents, special characters, and apostrophes (turning "O'Connor" into "OCONNOR").
# Replaces & signs with the word "AND".
# Removes store numbers (like #4021).
# Removes corporate endings (like LLC or INC) only if they are at the end.
# Replaces all extra spaces and punctuation with single clean spaces and trims the edges.

def normalize_name(name: str) -> str:
    """Apply deterministic syntax-only normalization to a name.
    
    This function cleans up a restaurant or brand name by normalizing Unicode characters,
    converting to uppercase, removing punctuation like apostrophes, replacing '&' with 'AND',
    stripping out store identifiers (e.g., #4021), removing legal suffixes (e.g., LLC, INC),
    and collapsing multiple spaces into a single space. The result is a clean, consistent name
    that can be reliably matched against other names in the system.
    """

    if not isinstance(name, str):
        raise TypeError("Restaurant and brand names must be strings.")

    normalized = unicodedata.normalize("NFKD", name)
    normalized = (
        normalized.encode("ascii", errors="ignore").decode("ascii").upper()
    )
    normalized = re.sub(r"['’`]", "", normalized)
    normalized = normalized.replace("&", " AND ")
    # A leading hash is strong evidence of a store identifier. Accept both
    # numeric and alphanumeric forms, such as #4021 and # C1016.
    normalized = re.sub(
        r"#\s*[A-Z0-9]+(?:[-/][A-Z0-9]+)*\b",
        " ",
        normalized,
    )
    # Remove legal words only as trailing suffixes, preserving names such as
    # LTD PIZZA and descriptors after an operator company name.
    normalized = LEGAL_SUFFIX_PATTERN.sub(" ", normalized)
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()

#  load_aliases(): Reads your brand alias CSV file so the script knows how to map alternative names to official brand names (e.g., mapping "MCD" to "MCDONALDS").
def load_aliases(path: Path) -> dict[str, str]:
    """Load reviewed aliases keyed by their normalized source value."""

    rows = _read_reference_rows(
        path,
        {"alias_name_normalized", "brand_name_normalized"},
    )
    aliases: dict[str, str] = {}

    for row in rows:
        alias = normalize_name(row["alias_name_normalized"])
        brand = normalize_name(row["brand_name_normalized"])

        if not alias or not brand:
            raise ValueError(f"{path.name} contains a blank name.")
        if alias in aliases and aliases[alias] != brand:
            raise ValueError(
                f"Conflicting targets for alias {alias!r} in {path.name}."
            )

        aliases[alias] = brand

    return aliases

# load_co_brand_associations(): Reads your co-brand file. This ensures that if a single storefront houses two brands together (like a combined Taco Bell and KFC), they don't get accidentally crushed into a single weird name.
def load_co_brand_associations(path: Path) -> dict[str, tuple[str, ...]]:
    """Load reviewed composite-name-to-brand associations."""

    rows = _read_reference_rows(
        path,
        {"location_name_normalized", "brand_name_normalized"},
    )
    associations: defaultdict[str, list[str]] = defaultdict(list)

    for row in rows:
        location_name = normalize_name(row["location_name_normalized"])
        brand_name = normalize_name(row["brand_name_normalized"])

        if not location_name or not brand_name:
            raise ValueError(f"{path.name} contains a blank name.")
        if brand_name not in associations[location_name]:
            associations[location_name].append(brand_name)

    return {
        location_name: tuple(brand_names)
        for location_name, brand_names in associations.items()
    }


def load_brand_registry(path: Path) -> set[str]:
    """Load the final list of canonical fast-food brand names."""

    rows = _read_reference_rows(path, {"brand_name_normalized"})
    brands = {
        normalize_name(row["brand_name_normalized"])
        for row in rows
        if row["brand_name_normalized"].strip()
    }

    if not brands:
        raise ValueError(f"{path.name} contains no brand names.")

    return brands


def load_name_references(
    reference_directory: Path,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], set[str]]:
    """Load aliases, co-brands, and the final brand registry together."""

    aliases = load_aliases(reference_directory / "brand_aliases.csv")
    co_brands = load_co_brand_associations(
        reference_directory / "co_brand_associations.csv"
    )
    fast_food_brands = load_brand_registry(
        reference_directory / "fast_food_brands.csv"
    )
    return aliases, co_brands, fast_food_brands

# canonicalize_name(): Cleans a name using normalize_name() and then swaps it for its official alias if one exists.
def canonicalize_name(name: str, aliases: dict[str, str]) -> str:
    """Normalize a name and apply a reviewed whole-name alias."""

    normalized = normalize_name(name)
    return aliases.get(normalized, normalized)

# brand_candidates(): Checks if a restaurant name is a known co-brand. 
# If it is, it returns both brands; otherwise, it returns the single clean brand name.
def brand_candidates(
    name: str,
    aliases: dict[str, str],
    co_brands: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Return exact-join candidates without destroying composite names."""

    normalized = normalize_name(name)
    if normalized in co_brands:
        return co_brands[normalized]

    canonical = aliases.get(normalized, normalized)
    return (canonical,) if canonical else ()

# load_brand_classification_overrides(): Reads a CSV file containing explicit INCLUDE/EXCLUDE decisions for brands derived from OSM data. 
# This allows for manual review and correction of brand classifications.
def load_brand_classification_overrides(path: Path) -> dict[str, str]:
    """Load explicit INCLUDE/EXCLUDE decisions for the OSM-derived list."""

    rows = _read_reference_rows(
        path,
        {"brand_name_normalized", "action", "reason"},
    )
    overrides: dict[str, str] = {}

    for row in rows:
        brand = normalize_name(row["brand_name_normalized"])
        action = row["action"].strip().upper()

        if not brand:
            raise ValueError(f"{path.name} contains a blank brand.")
        if action not in {"INCLUDE", "EXCLUDE"}:
            raise ValueError(
                f"Invalid action {action!r} for {brand!r} in {path.name}."
            )
        if brand in overrides and overrides[brand] != action:
            raise ValueError(
                f"Conflicting actions for brand {brand!r} in {path.name}."
            )

        overrides[brand] = action

    return overrides

# apply_brand_classification_overrides(): Applies the INCLUDE/EXCLUDE decisions to a set of brands, returning a cleaned-up set based on the manual reviews.
def apply_brand_classification_overrides(
    brands: set[str],
    overrides: dict[str, str],
) -> set[str]:
    """Return a normalized brand set after reviewed scope decisions."""

    reviewed = {normalize_name(brand) for brand in brands if brand}
    for brand, action in overrides.items():
        if action == "INCLUDE":
            reviewed.add(brand)
        else:
            reviewed.discard(brand)
    return reviewed

# this module is designed to be imported by the Phase 1 scripts, not run directly
