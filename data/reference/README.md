# Static reference data

These files support maps, neighborhood labels, and fast-food brand
confirmation. They are downloaded manually and do not pass through the
Bronze, Silver, or daily Airflow pipeline.

## Files

### `nyc_borough_boundaries.geojson` - Borough API output file

- Source: NYC Open Data
- Dataset: Borough Boundaries
- Dataset ID: `gthc-hcne`
- Use: Borough map shading on dashboard Pages 1 and 2

### `nyc_zcta_boundaries.geojson` - NYC ZipCode API File

- Source: NYC Open Data
- Dataset: ZIP Code Tabulation Areas
- Dataset ID: `35j5-n34v`
- Use: ZIP-level geography and map/navigation support

### `zip_to_nta.csv` - ZIP-to-NTA Lookup Table

- Source inputs:
  - NYC ZCTA boundaries: `35j5-n34v`
  - NYC 2020 NTA boundaries: `9nt8-h7nd`
- Method: Each ZCTA is assigned to the NTA with the largest geographic
  polygon overlap.
- Columns:
  - `zip`
  - `nta_code`
  - `nta_name`
  - `borough`
- Limitation: ZIP/ZCTA and NTA boundaries are not naturally one-to-one.
  The assigned NTA is therefore a dominant-area approximation.

### `fast_food_brands.csv` - Fast-Food Output file

## Brand normalization and harmonization

Brand values are standardized to uppercase, punctuation is removed,
whitespace is collapsed, hash-prefixed store identifiers are removed, and
common legal suffixes are removed only when they occur at the end. Descriptive
words and location qualifiers are preserved unless a reviewed whole-name alias
maps them to a canonical brand.

Evidence-backed historical aliases are then mapped to one canonical
brand name. For example:

- `DUNKIN DONUTS` → `DUNKIN`

The same normalization and alias rules must later be applied to DOHMH
restaurant names before joining them to this reference list.

- Source: OpenStreetMap contributors through the Overpass API
- Selection: NYC features tagged with both `amenity=fast_food` and `brand`
- Column: `brand_name_normalized`
- Use: Confirms fast-food brands independently of the three-location
  chain-detection rule
- License/attribution: © OpenStreetMap contributors, Open Database License

### `brand_aliases.csv` - Hand-curated file

- Columns: `alias_name_normalized`, `brand_name_normalized`
- Use: reviewed historical or alternate whole-name aliases
- Rule: both columns use the shared syntax normalization before lookup

### `brand_classification_overrides.csv` - Hand-curated file

- Columns: `brand_name_normalized`, `action`, `reason`
- Use: explicit QSR-scope decisions applied after the OpenStreetMap download
- `INCLUDE`: reviewed counter-service food, beverage, or dessert chains that
  OSM may classify as `cafe` or `ice_cream` instead of `fast_food`
- `EXCLUDE`: non-restaurant brands incorrectly returned by source tagging
- Current policy: the dashboard's confirmed-fast-food flag uses this broader
  quick-service scope; the reason column documents every manual exception

### `co_brand_associations.csv` - Hand-curated file

- Columns: `location_name_normalized`, `brand_name_normalized`
- Grain: one row per composite location name and constituent brand
- Use: preserves multiple brands at one location while producing exact-join
  brand candidates
- Rule: separators such as `/`, `&`, commas, and `AND` never create an
  association automatically; each composite name must be reviewed

DOHMH `dba` remains unchanged. Its normalized composite name remains one
restaurant-level value for the three-location chain heuristic. A separate
one-to-many association is used for brand confirmation, and
`is_confirmed_fast_food` is true when any associated canonical brand exactly
matches `fast_food_brands.brand_name_normalized`.

## Refresh policy

These files are downloaded once for the MVP and refreshed only when their
reference sources materially change.

## Pipeline treatment

These files are not Bronze or Silver data. The Streamlit application reads
the geographic files directly, while dbt uses the ZIP/NTA and brand lookup
files when building the Gold layer.
