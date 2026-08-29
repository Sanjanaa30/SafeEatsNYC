"""Tests for shared restaurant and brand name harmonization."""

from pathlib import Path

import pytest

from ingestion.name_normalization import (
    apply_brand_classification_overrides,
    brand_candidates,
    canonicalize_name,
    load_aliases,
    load_brand_classification_overrides,
    load_co_brand_associations,
    normalize_name,
)

# The script starts by loading your actual reference files (brand_aliases.csv, co_brand_associations.csv, and brand_classification_overrides.csv) so the tests can use real-world rules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIRECTORY = PROJECT_ROOT / "data" / "reference"
ALIASES = load_aliases(REFERENCE_DIRECTORY / "brand_aliases.csv")
CO_BRANDS = load_co_brand_associations(
    REFERENCE_DIRECTORY / "co_brand_associations.csv"
)
CLASSIFICATION_OVERRIDES = load_brand_classification_overrides(
    REFERENCE_DIRECTORY / "brand_classification_overrides.csv"
)

# test_dunkin_variants_share_one_canonical_name(): Checks that messy variations like "DUNKIN", "DUNKIN'", and "DUNKIN DONUTS" all map cleanly to the exact same official name ("DUNKIN").
def test_dunkin_variants_share_one_canonical_name() -> None:
    variants = ("DUNKIN", "DUNKIN'", "DUNKIN DONUTS")

    assert {
        canonicalize_name(name, ALIASES) for name in variants
    } == {"DUNKIN"}

# test_same_function_harmonizes_join_sides(): Ensures that a restaurant listed as "Dunkin Donuts #4021 LLC" matches the reference name "DUNKIN" perfectly after normalization.
def test_same_function_harmonizes_join_sides() -> None:
    restaurant_name = canonicalize_name("Dunkin Donuts #4021 LLC", ALIASES)
    reference_name = canonicalize_name("DUNKIN", ALIASES)

    assert restaurant_name == reference_name == "DUNKIN"

# test_reviewed_co_brand_preserves_both_brands(): Tests that a combined store like "DUNKIN',' BASKIN ROBBINS" correctly keeps both brands separate instead of squishing them together.
def test_reviewed_co_brand_preserves_both_brands() -> None:
    assert brand_candidates(
        "DUNKIN',' BASKIN ROBBINS",
        ALIASES,
        CO_BRANDS,
    ) == ("DUNKIN", "BASKIN ROBBINS")

# test_separator_does_not_automatically_create_co_brand(): Confirms that just because a name has an ampersand (like "JOE & THE JUICE"), it doesn't automatically get split into two separate brands—it stays a single proper name ("JOE AND THE JUICE").
def test_separator_does_not_automatically_create_co_brand() -> None:
    assert brand_candidates(
        "JOE & THE JUICE",
        ALIASES,
        CO_BRANDS,
    ) == ("JOE AND THE JUICE",)

# test_other_reviewed_co_brand_uses_same_policy(): Tests that another reviewed co-brand like "KFC / TACO BELL" is correctly split into its constituent brands.
def test_other_reviewed_co_brand_uses_same_policy() -> None:
    assert brand_candidates(
        "KFC / TACO BELL",
        ALIASES,
        CO_BRANDS,
    ) == ("KFC", "TACO BELL")

# test_known_brand_word_in_description_is_not_split(): Ensures that regular words inside a long description (like the word "FAMOUS" or "KIOSK") don't accidentally get treated as separate brand names.
def test_known_brand_word_in_description_is_not_split() -> None:
    name = "NATHAN'S FAMOUS KIOSK BY THE WONDER WHEEL"

    assert brand_candidates(name, ALIASES, CO_BRANDS) == (
        "NATHANS FAMOUS KIOSK BY THE WONDER WHEEL",
    )

# test_normalization_removes_punctuation_not_information(): Checks that punctuation is cleared out correctly while keeping words intact.
def test_normalization_removes_punctuation_not_information() -> None:
    assert normalize_name("AUNTIE ANNE'S/CINNABON") == (
        "AUNTIE ANNES CINNABON"
    )

# test_legal_suffix_is_removed_only_at_end(): Tests that corporate words like INC. or LLC are removed only when they appear at the very end of a name (making sure a place called "LTD PIZZA" doesn't lose its "LTD").
def test_legal_suffix_is_removed_only_at_end() -> None:
    assert normalize_name("MCDONALDS, INC.") == "MCDONALDS"
    assert normalize_name("LTD PIZZA") == "LTD PIZZA"
    assert normalize_name("EATALY NY LLC (KIOSK)") == (
        "EATALY NY LLC KIOSK"
    )


# test_alphanumeric_hash_store_id_is_removed(): Tests that store IDs prefixed with a hash (#) are correctly removed from the name.
def test_alphanumeric_hash_store_id_is_removed() -> None:
    assert normalize_name("RAISING CANE'S # C1016") == "RAISING CANES"
    assert normalize_name("CHIPOTLE #3641UY") == "CHIPOTLE"


@pytest.mark.parametrize(
    ("source_name", "expected"),
    [
        ("CHIPOTLE MEXICAN GRILL #2407", "CHIPOTLE"),
        ("POPEYES LOUISIANA KITCHEN", "POPEYES"),
        ("PAPA JOHN'S PIZZA", "PAPA JOHNS"),
        ("STARBUCKS COFFEE #123", "STARBUCKS"),
        ("TACO BELL CANTINA", "TACO BELL"),
    ],
)

# test_reviewed_chain_aliases(): A table of test cases (like turning "POPEYES LOUISIANA KITCHEN" into "POPEYES").
def test_reviewed_chain_aliases(source_name: str, expected: str) -> None:
    assert canonicalize_name(source_name, ALIASES) == expected

# test_unicode_accents_are_normalized_deterministically(): Checks that accented letters like "Café" safely become regular uppercase letters ("CAFE").
def test_unicode_accents_are_normalized_deterministically() -> None:
    assert normalize_name("Café") == "CAFE"

# test_non_string_name_fails_clearly(): Ensures that if someone accidentally passes empty data (None) instead of text, the code crashes safely with a clear TypeError.
def test_non_string_name_fails_clearly() -> None:
    """Ensure that non-string inputs raise a TypeError with a clear message."""
    with pytest.raises(TypeError, match="must be strings"):
        normalize_name(None)  # type: ignore[arg-type]

# test_brand_scope_overrides_include_qsr_and_exclude_retail(): Verifies that your override rules successfully force-include fast food chains while keeping non-food retail stores (like "BOOST MOBILE") out of the list.
def test_brand_scope_overrides_include_qsr_and_exclude_retail() -> None:
    reviewed = apply_brand_classification_overrides(
        {"DUNKIN", "BOOST MOBILE"},
        CLASSIFICATION_OVERRIDES,
    )

    assert {"DUNKIN", "BASKIN ROBBINS", "CARVEL", "STARBUCKS"} <= reviewed
    assert "BOOST MOBILE" not in reviewed

# test_conflicting_alias_targets_fail(): Ensures that if the alias file has conflicting targets for the same name, it raises a clear error.
def test_conflicting_alias_targets_fail(tmp_path: Path) -> None:
    alias_path = tmp_path / "aliases.csv"
    alias_path.write_text(
        "alias_name_normalized,brand_name_normalized\n"
        "SAME NAME,BRAND ONE\n"
        "SAME NAME,BRAND TWO\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Conflicting targets"):
        load_aliases(alias_path)

# test_missing_reference_columns_fail(): Checks that if the reference file is missing required columns, it raises a clear error.
def test_missing_reference_columns_fail(tmp_path: Path) -> None:
    alias_path = tmp_path / "aliases.csv"
    alias_path.write_text("wrong_column\nvalue\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        load_aliases(alias_path)

# test_reviewed_aliases_are_idempotent(): Verifies that applying the alias normalization repeatedly doesn't change the result.
def test_reviewed_aliases_are_idempotent() -> None:
    for alias, canonical in ALIASES.items():
        assert normalize_name(alias) == alias
        assert canonicalize_name(alias, ALIASES) == canonical
        assert canonicalize_name(canonical, ALIASES) == canonical

# test_co_brand_associations_have_multiple_unique_brands(): Checks that every recorded co-brand entry actually contains at least two distinct, unique brands.
def test_co_brand_associations_have_multiple_unique_brands() -> None:
    for location_name, brands in CO_BRANDS.items():
        assert normalize_name(location_name) == location_name
        assert len(brands) >= 2
        assert len(brands) == len(set(brands))

# test_final_fast_food_registry_is_clean_and_in_scope(): Opens your final fast_food_brands.csv file to verify it is sorted alphabetically, contains major chains like Starbuck/Carvel, and completely excludes non-food brands.
def test_final_fast_food_registry_is_clean_and_in_scope() -> None:
    registry_path = REFERENCE_DIRECTORY / "fast_food_brands.csv"
    lines = registry_path.read_text(encoding="utf-8").splitlines()[1:]

    assert lines == sorted(set(lines))
    assert {"BASKIN ROBBINS", "CARVEL", "STARBUCKS"} <= set(lines)
    assert {"BOOST MOBILE", "BREITLING", "CHINA WOK", "COSTCO", "JACKS", "T MOBILE"}.isdisjoint(
        lines
    )
