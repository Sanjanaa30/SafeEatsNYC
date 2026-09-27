# Static reference data

The files in `data/reference/` add geographic labels and reviewed restaurant
brand information to SafeEats NYC.

They are different from the daily inspection and 311 data:

- Daily source data moves through the Bronze, Silver, and Gold layers.
- Reference files are downloaded or reviewed separately and change less often.
- A reference refresh should be reviewed before its results are used by the
  pipeline or website.

## File summary

| File | Purpose | Source |
|---|---|---|
| `nyc_borough_boundaries.geojson` | Draws the five boroughs on the correlation map. | NYC Open Data `gthc-hcne` |
| `nyc_zcta_boundaries.geojson` | Provides NYC ZIP Code Tabulation Area boundaries. | NYC Open Data `35j5-n34v` |
| `zip_to_nta.csv` | Gives each ZIP a practical neighborhood and borough label. | NYC ZCTA and 2020 NTA boundaries |
| `fast_food_brands.csv` | Lists normalized fast-food and reviewed quick-service brands. | OpenStreetMap plus reviewed overrides |
| `brand_aliases.csv` | Maps an older or alternate brand name to one standard name. | Manual review |
| `brand_classification_overrides.csv` | Explicitly includes or excludes unusual brand classifications. | Manual review |
| `co_brand_associations.csv` | Records locations that contain more than one reviewed brand. | Manual review |

## Geographic files

### Borough boundaries

`nyc_borough_boundaries.geojson` contains one shape for each NYC borough. The
website uses a copy at `frontend/public/maps/nyc_borough_boundaries.geojson` so
the browser can draw the correlation map without AWS access.

When the source boundary file is refreshed, review it and update the frontend
copy before publishing the website.

### ZIP boundaries

`nyc_zcta_boundaries.geojson` contains ZIP Code Tabulation Area shapes. A ZCTA
is the Census Bureau's geographic approximation of a postal ZIP code.

### ZIP-to-neighborhood lookup

`zip_to_nta.csv` contains:

- `zip`: five-digit ZIP code
- `nta_code`: NYC Neighborhood Tabulation Area code
- `nta_name`: neighborhood name
- `borough`: borough name

A ZIP and a neighborhood do not always have the same boundary. The preparation
script assigns each ZIP to the neighborhood with the largest overlapping area.
This makes the lookup useful for labels, but it is still an approximation.

dbt loads this CSV as a seed and uses it when building restaurant dimensions.

## Brand files

### Fast-food brand list

`fast_food_brands.csv` contains one normalized brand per row. The base list
comes from OpenStreetMap features in NYC tagged with both `amenity=fast_food`
and `brand`.

The list is used to confirm quick-service brands independently of the rule that
identifies restaurant groups from repeated names and locations.

OpenStreetMap data is provided by OpenStreetMap contributors under the Open
Database License.

### Brand aliases

`brand_aliases.csv` maps reviewed alternate names to one standard brand name.
For example:

```text
DUNKIN DONUTS -> DUNKIN
```

Both sides of the mapping use the same name-cleaning rules.

### Classification overrides

`brand_classification_overrides.csv` contains:

- `brand_name_normalized`
- `action`
- `reason`

`INCLUDE` adds a reviewed food, drink, or dessert brand that OpenStreetMap may
classify as a cafe or ice-cream shop instead of fast food. `EXCLUDE` removes a
non-restaurant or incorrectly tagged brand. The reason records why the manual
decision was made.

### Co-brand associations

`co_brand_associations.csv` contains:

- `location_name_normalized`
- `brand_name_normalized`

It allows one restaurant location name to point to several brands. Separators
such as `/`, `&`, commas, or `AND` do not create associations automatically.
Each co-brand name must be reviewed first.

The original DOHMH restaurant name is preserved. Name normalization creates a
separate matching value and does not rewrite the official name shown to users.

## Name normalization

For matching only, names are converted to uppercase, punctuation and repeated
spaces are removed, store numbers beginning with `#` are removed, and common
legal suffixes are removed when they appear at the end. Reviewed aliases are
then applied.

This improves matching, but similar names are not always the same business.
Uncertain group or brand matches should remain in a review queue instead of
being joined automatically.

## Refresh the generated files

From the repository root, activate the Python environment and run:

```powershell
python ingestion/download_reference_data.py
```

The script:

1. Downloads borough boundaries.
2. Downloads ZCTA boundaries.
3. Temporarily downloads NTA boundaries.
4. Builds the ZIP-to-NTA lookup using the largest polygon overlap.
5. Downloads OpenStreetMap fast-food brands.
6. Applies the reviewed aliases and classification overrides.
7. Validates the outputs before finishing.

The command writes the four generated files. It does not overwrite the three
manual review files unless they are edited separately.

## Review checklist

After a refresh:

1. Confirm that the borough file still contains exactly five boroughs.
2. Confirm that the ZCTA and ZIP lookup contain the expected NYC coverage.
3. Review brand additions, removals, aliases, and overrides.
4. Confirm that co-brand mappings still represent real shared locations.
5. Copy the approved borough GeoJSON to `frontend/public/maps/`.
6. Rebuild the affected Silver and Gold outputs before relying on the changes.

Reference data is refreshed only when a source or a reviewed mapping changes
materially; it is not part of the normal daily Airflow run.
