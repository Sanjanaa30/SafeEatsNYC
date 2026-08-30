# SafeEats NYC — Phase 1 MVP Scope

## Purpose

SafeEats NYC combines NYC restaurant inspections and relevant 311 complaints
to support restaurant safety lookup, borough comparisons, complaint/inspection
analysis, and one predictive B/C-grade risk model.

## What Phase 1 did

Phase 1 prepared and studied the data before building the production pipeline.
It completed these tasks in order:

1. Confirmed that Python, Docker, and the project folders were usable.
2. Downloaded small samples from the DOHMH and 311 APIs.
3. Profiled the samples to understand their fields, quality, and grain.
4. Downloaded the geographic and fast-food/QSR reference data.
5. Created one shared restaurant-name normalization process for DOHMH names
   and reference-brand names.
6. Profiled all distinct live DOHMH restaurant names, not only the sample.
7. Created review queues for unclear aliases and possible co-brands.
8. Documented the MVP scope, assumptions, limitations, and expected pages.
9. Ran the Phase 1 tests and final audit.

Phase 1 did not download every DOHMH inspection row into the project. That
full, incremental row-level ingestion belongs to Phase 2.

## Phase 1 file and data flow

### 0. Prepare the project

```text
requirements.txt ─────────> project Python environment (.venv)
docker-compose.yml ───────> Docker Compose availability check
project folders ──────────> places for ingestion code, data, docs, and tests
```

This step confirmed that the local tools and repository structure needed for
later phases were ready. It did not create a production data pipeline.

### 1. Download API samples

```text
NYC DOHMH API (43nn-pn8j) ──┐
                            ├─> ingestion/pull_samples.py
NYC 311 API (erm2-nwe9) ────┘             │
                                          ├─> data/samples/dohmh_inspections_sample.json
                                          └─> data/samples/311_food_pest_sample.json
```

`ingestion/pull_samples.py` requests 1,000 recent DOHMH rows and 1,000
relevant 311 rows. The JSON files are small local samples used to understand
the sources before full ingestion.

### 2. Profile the samples

```text
data/samples/dohmh_inspections_sample.json ─┐
                                            ├─> ingestion/profile_samples.py
data/samples/311_food_pest_sample.json ─────┘                │
                                                             └─> docs/project_documents/data_profile.md
```

`ingestion/profile_samples.py` checks columns, missing values, identifiers,
dates, coordinates, duplicates, complaint types, and dataset grain. It writes
the findings to `docs/project_documents/data_profile.md`.

### 3. Build static reference files

```text
NYC borough, ZCTA, and NTA APIs ─┐
                                 ├─> ingestion/download_reference_data.py
OpenStreetMap brand data ────────┘                 │
                                                   ├─> data/reference/nyc_borough_boundaries.geojson
                                                   ├─> data/reference/nyc_zcta_boundaries.geojson
                                                   ├─> data/reference/zip_to_nta.csv
                                                   └─> data/reference/fast_food_brands.csv
```

The script downloads map boundaries, assigns each ZIP/ZCTA to its dominant
NTA by geographic overlap, and creates the canonical fast-food/QSR registry.
It also uses these reviewed inputs:

- `data/reference/brand_aliases.csv` maps alternate names to canonical brands.
- `data/reference/co_brand_associations.csv` preserves the individual brands
  at reviewed co-branded locations.
- `data/reference/brand_classification_overrides.csv` records explicit brand
  inclusion and exclusion decisions.
- `docs/project_documents/README.md` explains the files stored under
  `data/reference/` and their columns.

### 4. Normalize and profile all restaurant names

```text
Live distinct DOHMH camis/dba pairs ────────────────┐
data/reference/fast_food_brands.csv ────────────────┤
data/reference/brand_aliases.csv ───────────────────┤
data/reference/co_brand_associations.csv ───────────┼─> ingestion/profile_restaurant_names.py
data/reference/brand_classification_overrides.csv ───┤                  │
ingestion/name_normalization.py (shared rules) ──────┘                  │
                                                                       │
                                                                       ├─> docs/project_documents/restaurant_name_profile.md
                                                                       ├─> docs/brand_alias_review_queue.csv
                                                                       └─> docs/co_brand_review_queue.csv
```

`ingestion/name_normalization.py` contains the shared rules used on both sides
of a name match. For example, a DOHMH name such as `DUNKIN DONUTS` and the
reference name `DUNKIN` pass through the same cleanup and alias logic before
exact matching.

`ingestion/profile_restaurant_names.py` retrieves every distinct live
`camis`/`dba` pair, applies those shared rules, counts confirmed brand matches,
and writes the name report and human-review queues. A reviewed co-brand keeps
its original DBA and can produce multiple brand associations. An unknown
combination stays in a queue instead of being accepted or stripped silently.

### 5. Validate and document Phase 1

```text
tests/test_name_normalization.py ─> verifies normalization, aliases,
                                    co-brands, and brand classification

All Phase 1 findings ─────────────> docs/project_documents/phase1_scope.md
```

## How to run Phase 1

From the project root in PowerShell, run:

```powershell
.\.venv\Scripts\python.exe ingestion\pull_samples.py
.\.venv\Scripts\python.exe ingestion\download_reference_data.py
.\.venv\Scripts\python.exe ingestion\profile_samples.py
.\.venv\Scripts\python.exe ingestion\profile_restaurant_names.py
.\.venv\Scripts\python.exe -m pytest tests\test_name_normalization.py -q
```

Run the commands in this order because later scripts use files created by
earlier scripts. Existing files at the listed output paths are overwritten.
Because the NYC APIs are live, rerunning the scripts can produce newer values.

## Phase 1 results

- 1,000 recent DOHMH inspection/violation sample rows were saved.
- 1,000 filtered 311 food, food-poisoning, and rodent rows were saved.
- The reference data contains 5 boroughs, 221 ZCTA features, and 221 ZIP-to-NTA
  lookup rows.
- The reviewed name references contain 109 canonical fast-food/QSR brands,
  102 aliases, and 73 co-brand associations.
- The full live-name profile covered 31,386 distinct DOHMH `camis`/`dba`
  pairs—not only the 1,000-row sample.
- It confirmed 2,988 DOHMH restaurant identifiers as fast-food/QSR matches;
  161 were matched through reviewed co-brand associations.
- All 22 Phase 1 name-normalization tests passed in the final audit.

## Included in the MVP

- Restaurant lookup by name and ZIP/neighborhood
- Borough, cuisine, grade, and distance filters
- Current grade, score, inspection date, and violation details
- Three-year restaurant grade history and consistency indicators
- Repeat-critical-violation and recently-improved-to-A indicators
- Nearby Grade A restaurant discovery
- Citywide and borough-level grade, cuisine, and violation summaries
- Weekly 311 complaint versus critical-inspection correlation
- Approximate complaint-to-restaurant matching within 100 meters
- Three-location chain detection plus reviewed fast-food/QSR confirmation
- One B/C-grade risk classifier with explanatory factors

## Intentionally excluded

| Feature | Reason |
|---|---|
| Price or budget filters | The selected NYC datasets contain no price tier |
| Dietary labels | Vegan, halal, and gluten-free attributes are not available reliably |
| Open-now or operating-hours status | DOHMH does not provide real-time hours |
| Walking routes or navigation | Requires a routing or places service outside the MVP |
| Survey-based recommendations | No real survey dataset is included |
| Live GPS-based discovery | Requires additional live-location functionality |
| Type 2 restaurant history | The MVP uses current restaurant attributes and inspection history |
| Multiple ML models | The MVP intentionally contains one risk classifier |

## Datasets

| Dataset | Role | Phase 1 material |
|---|---|---|
| DOHMH Restaurant Inspection Results (`43nn-pn8j`) | Inspection, violation, grade, restaurant, and location data | 1,000-row local sample plus a live full-population name profile |
| NYC 311 Service Requests (`erm2-nwe9`) | Food, establishment, and rodent complaints | 1,000-row filtered local sample |
| NYC Borough Boundaries (`gthc-hcne`) | Borough map geometry | Static GeoJSON, 5 features |
| NYC ZCTA Boundaries (`35j5-n34v`) | ZIP-level map/navigation geometry | Static GeoJSON, 221 features |
| NYC 2020 NTA Boundaries (`9nt8-h7nd`) | Neighborhood assignment source | Used to build the ZIP-to-NTA lookup |
| ZIP-to-NTA lookup | Dominant neighborhood and borough per ZIP | Static CSV, 221 ZIP rows |
| OSM fast-food brands plus reviewed overrides | Fast-food/QSR confirmation | 109 canonical brands |
| Brand aliases and co-brand associations | Shared canonicalization and multi-brand preservation | Reviewed static CSV files |

At the final Phase 1 audit on August 28, 2026, the live DOHMH source contained
296,188 inspection/violation rows and 31,387 distinct CAMIS identifiers. The
name profile covered 31,386 CAMIS/DBA pairs; one source record had no DBA. Phase 1 did not download
all 296,188 rows locally. Full row-level ingestion begins in the pipeline phase.

## Dataset grain

| Dataset or artifact | Grain |
|---|---|
| DOHMH source | One row per cited violation within an inspection; inspections can therefore span multiple rows |
| DOHMH name profile | One distinct `camis` and `dba` pair returned by the live source |
| 311 source | One row per service request, keyed by `unique_key` |
| Borough boundaries | One feature per NYC borough |
| ZCTA boundaries | One feature per NYC ZCTA |
| ZIP-to-NTA lookup | One dominant NTA assignment per ZIP/ZCTA |
| Fast-food registry | One canonical brand per row |
| Brand aliases | One reviewed alternate name to canonical brand mapping per row |
| Co-brand associations | One composite location name and constituent brand per row |

## Important assumptions

- `camis` is the natural restaurant identifier in DOHMH.
- Source JSON is preserved unchanged in Bronze; cleaning occurs downstream.
- `1900-01-01` is treated as a not-yet-inspected sentinel rather than a real
  inspection date.
- Source grades such as N, Z, and P remain available in Silver; graded Gold
  metrics apply documented A/B/C rules.
- A chain has at least three distinct CAMIS values sharing a canonical name.
- Fast-food/QSR confirmation is independent of the three-location heuristic.
- DOHMH names and brand references use the same syntax normalization and alias
  rules. Co-brands produce multiple exact-match candidates without replacing
  the original DBA.
- New alias and co-brand candidates enter review queues and are never accepted
  solely because of punctuation or substring detection.
- A 311 complaint is associated with the nearest restaurant only when it is
  within approximately 100 meters. Proximity does not prove responsibility.
- ZIP-to-NTA assignment uses the largest polygon overlap and is an
  approximation because ZIP and NTA boundaries are not one-to-one.
- Correlation between complaints and inspections is descriptive, not causal.
- The three-location chain threshold and 100-meter distance are tunable MVP
  parameters, not universal facts.

## Known limitations

- Phase 1 field-quality findings come from recent 1,000-row samples; only the
  restaurant-name profile queried the full live DOHMH population.
- The live source changes as NYC updates restaurant and inspection records.
- Missing, zero, or out-of-NYC coordinates cannot be geospatially matched.
- Similar restaurant names can belong to unrelated businesses; ambiguous
  aliases remain unmatched until reviewed.
- Brand coverage depends on OpenStreetMap tagging plus documented inclusion and
  exclusion overrides.
- ZIP-to-NTA labels represent dominant geographic overlap, not exact address
  containment.
- DOHMH does not provide price, dietary, hours, or walking-route data.

## Expected dashboard pages

1. **City & Borough Safety Overview** — KPIs, grade distribution, cuisine
   performance, and common violations.
2. **Violations & 311 Correlation** — weekly trends, correlation summary, and
   geospatial overlap.
3. **SafeEats Restaurant Finder** — restaurant search, filters, history,
   nearby Grade A options, and fast-food chain summaries.
4. **Predictive Risk** — B/C-grade risk, contributing factors, and a citywide
   high-risk list.

## Phase 1 completion checklist

- [x] Repository folders separate ingestion, orchestration, transformation,
  geospatial, ML, dashboard, data, documentation, and tests.
- [x] Python is usable (`Python 3.13.3` in the project virtual environment).
- [x] Docker is usable (`Docker 29.5.3`); this machine uses the standalone
  `docker-compose` command (`v5.1.4`).
- [x] Both NYC APIs return and save validated 1,000-row samples.
- [x] Dataset fields, missingness, dates, coordinates, duplicates, and grain
  have been profiled and documented.
- [x] Static geographic and brand reference files are downloaded and validated.
- [x] Shared restaurant/brand normalization, aliases, co-brands, and review
  queues are documented and tested.
- [x] MVP scope, assumptions, exclusions, grain, limitations, and dashboard
  pages are documented here.

Phase 1 is complete. The next build step is incremental ingestion to S3 Bronze.
