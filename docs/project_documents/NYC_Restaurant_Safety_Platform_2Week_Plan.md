# NYC Restaurant Safety & Consumer Intelligence Platform
### 2-Week Build Plan (Fresher DE Portfolio Project) — v2

---

## 0. Problem Statement

NYC publishes restaurant health inspection results and 311 complaint data, but the two live in separate, hard-to-use city systems. A regular diner can't easily tell if a restaurant nearby is currently safe, whether its grade has been slipping, or whether a nearby rat complaint means anything. At the same time, that same raw inspection history has a pattern in it — restaurants that are heading toward a bad grade usually show warning signs beforehand (repeat critical violations, complaint spikes, time since last check).

This project builds a data pipeline and dashboard that pulls inspection and complaint data on a regular schedule, cleans and joins it, and turns it into three things: (1) a simple way for anyone to look up a restaurant's safety record, (2) borough- and citywide views of where NYC's food safety problems are concentrated, and (3) a model that flags restaurants at risk of a B/C grade before their next inspection happens.

---

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| Dashboard tool | **Streamlit** | Free, code-based, fast to deploy |
| Warehouse query engine | **Athena on S3 Parquet** | Serverless SQL over your Gold layer, no cluster to manage |
| Airflow | **Local via Docker Compose, 1 DAG, ~6 tasks** | Enough to demonstrate orchestration without fighting infra all week |
| Geospatial matching | **Lat/long distance threshold (haversine, ~100m)** | 10x faster to build than fuzzy address matching, still legitimate for your resume |
| ML scope | **1 model only: B/C grade risk classifier** | Matches your 10% AI/ML budget |

---

## 2. MVP Business Questions (build these)

**Predictive / ML**
- Q1: Which restaurants are at risk of a B/C grade? → risk gauge + top factors

**Correlation**
- Q2: Do 311 complaints correlate with inspection failures? → time-series only (Pearson or lagged cross-correlation on weekly aggregates, no ML)

**Borough-wise**
- Which borough has the highest % Grade A (100% stacked bar)
- Cleanest cuisines per borough (heatmap)
- Most common violations per borough (ranked bar + filter)

**Customer lookup (Page 3 core)**
- Current grade + inspection date for a restaurant
- Grade A nearby, filtered by cuisine (+ budget if built — see note below)
- Repeated critical violations flag
- Grade consistency over last 3 years
- Days since last inspection
- Restaurants that recently went B/C → A again

**Citywide + Borough cards**
- All 6 citywide cards
- All 4 borough filterable cards

**Data granularity**
- NYC → Borough → ZIP/neighborhood → Restaurant navigation
- Totals AND normalized (per 100 restaurants / per 1,000 restaurants) shown together

**Note on "budget" filter:** DOHMH data has no price-tier field. Ship the finder for MVP with cuisine + distance + grade filters only, and treat "budget" as blocked by data availability. That's a legitimate, interview-safe answer, not a shortcut.

---

## 3. Dataset

Two live sources feed the pipeline. Two more are static reference files used only for maps and labels — they never go through Bronze/Silver/Gold, they're just pulled once and stored as-is.

### 3.1 Live sources (go through the full pipeline)

**A. DOHMH Restaurant Inspection Results**
- Source: NYC Open Data (Socrata), dataset id `43nn-pn8j`
- Access: REST API (JSON), e.g. `https://data.cityofnewyork.us/resource/43nn-pn8j.json`
- Grain: one row per inspection per violation cited (a single inspection can have multiple rows)
- Key fields you'll actually use: `camis` (restaurant id), `dba` (name), `boro`, `building`+`street`+`zipcode` (address), `latitude`/`longitude`, `cuisine_description`, `inspection_date`, `action`, `violation_code`, `violation_description`, `critical_flag`, `score`, `grade`, `grade_date`
- Incremental pull strategy: filter on `inspection_date > last_successful_run_date` using Socrata's `$where` query parameter. Store the last successful timestamp in your audit log table so re-runs are idempotent.
- Update cadence: source updates daily; your pipeline runs daily too, so a small daily incremental pull is realistic (not a giant nightly reload).

**B. NYC 311 Service Requests**
- Source: NYC Open Data (Socrata), dataset id `erm2-nwe9`
- Access: same REST API pattern, filtered with `$where` on `complaint_type` (keep only food/pest-related types, e.g. "Food Poisoning", "Rodent", "Food Establishment") and `created_date`
- Key fields: `unique_key`, `created_date`, `complaint_type`, `descriptor`, `incident_zip`, `latitude`/`longitude`, `borough`, `status`
- Incremental pull strategy: same as above, filter on `created_date`

### 3.2 Static reference files (pulled once, not incremental, not part of Bronze/Silver/Gold pipeline)

**C. NYC Borough Boundaries / ZIP Code Tabulation Areas (GeoJSON)**
- Source: NYC Open Data / "Bytes of the Big Apple"
- Use: map shading (choropleth) on Pages 1–2 only. Downloaded once, saved as a static file the Streamlit app reads directly — it never touches S3/dbt.

**D. Neighborhood Tabulation Area (NTA) lookup — ZIP → neighborhood name**
- Source: NYC Open Data (Department of City Planning NTA lookup)
- Use: fills the gap between "ZIP code" and "neighborhood name" for your NYC → Borough → ZIP/neighborhood → Restaurant navigation, since DOHMH only gives you ZIP, not a clean neighborhood label. Loaded once as a small static lookup table (a handful of columns: zip, nta_name, borough), joined into `dim_restaurant` at dbt build time.

**E. Fast-food brand reference list**
- Source: a public brand-name list such as Datafiniti's "Fast Food Restaurants Across America" (Kaggle) or OpenStreetMap/Overture Maps POI data filtered to a NYC bounding box (`brand` tag). Neither is NYC/DOHMH-specific — they're general-purpose reference lists you're borrowing to validate chain names.
- Use: a single column of known fast-food brand names (normalized the same way as `name_normalized`), joined in at the same dbt staging step where chain detection happens (Day 7). It doesn't replace the location-count chain-detection logic — it adds one extra boolean so the pipeline can tell the difference between "any restaurant with 3+ locations" and "a confirmed fast-food brand." See Section 5 for exactly how the two flags work together.
- Not incremental — downloaded once, refreshed only occasionally (brand lists don't change often), never touches Bronze/Silver.

---

## 4. Architecture Diagram (detailed, plain-English walkthrough below it)

```
 ┌────────────────────────┐  ┌────────────────────┐
 │  DOHMH Inspection API  │  │      NYC 311 API   │
 │  (incremental, daily)  │  │(incremental, daily,│
 │                        │  │   food/pest filter)│
 └───────────┬────────────┘  └───────────┬────────┘
             │                           │
             └──────────────┬────────────┘
                             ▼
                  ┌───────────────────────┐
                  │  Python ingestion job │  ← reads last run timestamp
                  │  (Airflow task 1 & 2) │     from audit log, pulls only new rows
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  S3 Bronze (raw JSON) │  ← exact API response, untouched
                  │  partitioned by       │     partition = ingest date
                  │  ingest_date          │
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  PySpark clean job    │  ← dedupe, standardize name/address,
                  │  (Airflow task 3)     │     cast types, parse dates
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  S3 Silver (Parquet)  │  ← one clean table for inspections,
                  │  partitioned by       │     one for 311 complaints
                  │  year/month           │
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  Geospatial join job  │  ← haversine distance, attaches
                  │  (Airflow task 4)     │     nearest restaurant_id to each
                  │                       │     311 complaint (within ~100m)
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  dbt staging models   │  ← Athena external tables read
                  │  (Airflow task 5:     │     Silver Parquet directly, light
                  │   dbt run --staging)  │     renaming/typing only
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  dbt Gold models      │  ← star schema (facts + dims)
                  │  (Airflow task 5 cont:│     + 5 analytical marts
                  │   dbt run --gold)     │     + dbt tests
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │  Reconciliation check │  ← row counts: source API vs
                  │  (Airflow task 6)     │     Bronze vs Gold, logged to
                  │                       │     audit table, fails DAG if off
                  └───────────┬───────────┘
                             ▼
                  ┌───────────────────────┐
                  │       Athena          │  ← SQL query layer over Gold
                  │  (query engine)       │     Parquet in S3
                  └───────────┬───────────┘
                             ▼
        ┌────────────────────┴────────────────────┐
        ▼                                          ▼
┌─────────────────────┐                   ┌────────────────────────┐
│  Streamlit          │                   │  ML training script    │
│  dashboard          │ ◄──model file──── │  (reads Gold via       │
│  (4 pages)          │                   │   Athena, trains       │
│  + static GeoJSON/  │                   │   classifier, saves    │
│   NTA lookup files  │                   │   .pkl artifact)       │
└─────────────────────┘                   └────────────────────────┘

CI/CD:  GitHub Actions runs `dbt test` + pytest on every pull request
        (doesn't touch production data, runs against a small sample)
```

**In plain words, top to bottom:**
1. Two Airflow tasks call the DOHMH and 311 APIs, asking only for records newer than the last successful run.
2. Whatever comes back is dumped into S3 exactly as received (Bronze) — this is your "undo button" if a later step ever has a bug.
3. A PySpark job reads Bronze, removes duplicate inspection rows, cleans up restaurant names/addresses, and fixes data types — writes the result to Silver as Parquet.
4. A separate small job matches each 311 complaint to the nearest restaurant by GPS distance, so you can later ask "did complaints near this restaurant happen before its grade dropped?"
5. dbt reads Silver (via Athena) and builds two things: (a) staging models that just clean up column names/types, and (b) Gold models — the actual star schema and pre-aggregated marts your dashboard queries.
6. A reconciliation check compares row counts at each stage (API → Bronze → Gold) and fails the pipeline loudly if data goes missing, instead of silently serving stale/wrong numbers.
7. Streamlit queries Athena directly for anything not pre-aggregated, and reads the pre-built marts for anything that is. Page 4 also loads the saved ML model file to score restaurants live.
8. The two static files (GeoJSON boundaries, NTA lookup) are separate from all of this — they're small, unchanging, and just loaded straight into Streamlit/dbt without going through the pipeline.

---

## 5. Warehouse Model — Gold Star Schema (explained in plain words)

Think of it as one "facts" table per thing-that-happened (an inspection, a complaint), surrounded by "dimension" tables that describe the who/what/where/when. Facts are big and numeric; dimensions are smaller and descriptive. This is the standard pattern (Kimball star schema) — it's what makes "why is Bronx dirtier than Manhattan" a simple SQL join instead of a mess.

### Dimension tables (the "who/what/where/when")

**`dim_restaurant`** — one row per restaurant
| Column | Meaning |
|---|---|
| `restaurant_key` | surrogate key (auto-generated, used for joins) |
| `camis` | natural key from DOHMH (the restaurant's real-world id) |
| `name_standardized` | cleaned restaurant name |
| `name_normalized` | name standardized further for chain matching — see below |
| `address_standardized` | cleaned street address |
| `zip` | zip code |
| `nta_name` | neighborhood name (joined in from the static NTA lookup) |
| `borough_key` | FK → `dim_borough` |
| `cuisine` | e.g. "Pizza", "Mexican" |
| `latitude`, `longitude` | for maps and geospatial join |
| `is_chain` | true if 3+ distinct `camis` share the same `name_normalized` citywide — see below |
| `is_confirmed_fast_food` | true if `name_normalized` also matches a name in the fast-food brand reference list (dataset E in Section 3.2) — see below |
| `chain_key` | FK → `dim_chain`, null if `is_chain` is false |
| `is_current` | for MVP, always true — Type 1 (overwrite), no history tracking. (Type 2 / history tracking is a Backlog item, see below) |

### How chain detection actually works (no hand-typed list)

DOHMH data has no "is this a chain?" field, and a real NYC dataset has hundreds of chains (Subway, Dunkin', McDonald's, Domino's, etc. each with dozens to hundreds of locations), so this can't be a manually maintained list — it has to be derived in the pipeline, the same way NYC's own open-data team and most food-safety researchers do it. This uses **two independent flags**, both computed in the same dbt staging step:

1. **Normalize the name** (in the PySpark cleaning step, same place you already standardize name/address): uppercase, strip punctuation, collapse whitespace, remove hash-prefixed store identifiers (`#4021`, `# C1016`), and remove legal suffixes such as `LLC`/`INC` only at the end. Reviewed whole-name aliases handle historical names, brand descriptors, and location qualifiers; they are not stripped generically because those words can carry real identity. `"McDonald's #34521"` and `"MCDONALDS INC"` both become `MCDONALDS`, while `"LTD PIZZA"` remains `LTD PIZZA`.
2. **`is_chain` (location-count heuristic)**: group by `name_normalized`, count distinct `camis`. If a group has **3 or more distinct locations**, flag every row `is_chain = true` and assign it a `chain_key`. Fewer than 3 stays independent — a name shared by only 2 restaurants is more likely coincidence (e.g. two unrelated delis both called "Corner Deli") than an actual chain. This catches *any* repeat-location restaurant group — fast food or not. The "3+" threshold is a judgment call, not a hard rule — worth calling out as a tunable parameter, not a fact, if asked in interviews.
3. **`is_confirmed_fast_food` (brand-list lookup)**: apply the same normalization and reviewed alias rules to DOHMH names and the brand reference. Ordinary names produce one canonical exact-join candidate. Reviewed co-branded names produce one candidate per constituent brand without overwriting the restaurant-level composite name. Set `is_confirmed_fast_food = true` when any candidate exactly matches the fast-food reference. This is independent of the location count — it's possible for a real fast-food brand to have only 1–2 DOHMH locations in your data slice and still get this flag, and possible for a non-fast-food multi-location group (e.g. a 3-store local pizza mini-chain) to have `is_chain = true` but `is_confirmed_fast_food = false`.
4. Both flags land directly in `dim_restaurant`, computed by one dbt staging model (`stg_chain_flags`) that runs before the Gold layer. The brand match may use a one-to-many intermediate association so a co-branded restaurant remains one restaurant row. The association and alias seeds are reviewed reference data, not a replacement for the derived three-location chain heuristic.

**New dimension: `dim_chain`** — one row per detected chain (any `is_chain = true` group)
| Column | Meaning |
|---|---|
| `chain_key` | surrogate key |
| `chain_name` | the normalized brand name, cleaned up for display |
| `location_count` | how many distinct `camis` share this chain |
| `boroughs_present` | array/count of boroughs with at least one location |
| `is_confirmed_fast_food` | rolled up from `dim_restaurant` — lets the Finder's "Fast Food Chains" tab filter to just this subset, while still leaving other multi-location groups queryable if needed |

**`dim_date`** — one row per calendar day (standard date dimension: year, month, week, day, is_weekend, etc.) — lets you group anything by week/month/year without date-math in every query.

**`dim_borough`** — one row per borough (5 rows total)
| Column | Meaning |
|---|---|
| `borough_key` | surrogate key |
| `borough_name` | Manhattan, Brooklyn, Queens, Bronx, Staten Island |
| `total_restaurants` | count, used as the denominator for all "per 100 restaurants" normalized metrics |

**`dim_violation`** — one row per distinct violation code (code, description, `is_critical` flag)

**`dim_complaint_type`** — one row per distinct 311 complaint type (e.g. "Rodent", "Food Poisoning")

### Fact tables (the "what happened")

**`fact_inspection`** — grain: **one row per inspection per violation cited** (if an inspection has 3 violations, that's 3 rows sharing the same inspection_id)
| Column | Meaning |
|---|---|
| `inspection_id` | unique per inspection event |
| `restaurant_key` | FK → dim_restaurant |
| `date_key` | FK → dim_date (inspection date) |
| `violation_key` | FK → dim_violation |
| `borough_key` | FK → dim_borough (denormalized for fast filtering, avoids a join) |
| `score` | numeric inspection score |
| `grade` | A / B / C, derived from score (0–13=A, 14–27=B, 28+=C) |
| `is_critical` | true/false, copied from the violation for fast filtering |

**`fact_311_complaint`** — grain: **one row per complaint**
| Column | Meaning |
|---|---|
| `complaint_id` | natural key (`unique_key` from 311) |
| `restaurant_key` | FK → dim_restaurant, **nullable** — null if no restaurant was found within the ~100m match radius |
| `date_key` | FK → dim_date (created date) |
| `complaint_type_key` | FK → dim_complaint_type |
| `borough_key` | FK → dim_borough |
| `match_distance_meters` | how far the matched restaurant was, for transparency/debugging |

### Marts (pre-built on top of the star schema — one mart per dashboard chart, so Streamlit never has to compute aggregates itself)

| Mart | Feeds | What it pre-computes |
|---|---|---|
| `mart_borough_grade_summary` | Page 1 stacked bar + citywide/borough cards | % of restaurants at each grade, per borough, plus normalized per-100 rates |
| `mart_cuisine_borough_heatmap` | Page 1 heatmap | % Grade A by cuisine × borough |
| `mart_violation_by_borough` | Page 1 ranked bar | violation frequency per 100 restaurants, by borough, split critical vs. non-critical |
| `mart_weekly_311_vs_inspection` | Page 2 correlation chart | weekly complaint count vs. weekly critical-violation count, plus the correlation coefficient |
| `mart_restaurant_grade_history` | Page 3 lookup, "recently improved" list | per-restaurant grade timeline, days since last inspection, 3-year consistency flag, improved-to-A flag |
| `mart_chain_summary` | Page 3 "Fast Food Chains" section | one row per `chain_key`: location count, worst/best grade across locations, avg. score, boroughs present, `is_confirmed_fast_food` — the Finder tab filters this mart to `is_confirmed_fast_food = true` so it shows actual fast-food brands rather than every repeat-location group, and shows each as a single aggregated card instead of hundreds of duplicate-looking rows |

### How normalization actually works
`dim_borough.total_restaurants` is the denominator everywhere you see "per 100 restaurants" or "per 1,000 restaurants" — e.g. `mart_violation_by_borough.violations_per_100 = (violation_count / dim_borough.total_restaurants) * 100`. This is computed once in the mart, not recalculated in Streamlit, so every page shows consistent numbers.

### dbt tests to add on this schema (minimum set)
- `not_null` + `unique` on every surrogate/natural key
- `accepted_values` on `grade` (A/B/C only) and `is_critical`/`is_current` (boolean only)
- `relationships` test on every FK (e.g. every `restaurant_key` in `fact_inspection` must exist in `dim_restaurant`)
- `relationships` test: every non-null `chain_key` in `dim_restaurant` must exist in `dim_chain` (catches bugs in the chain-matching step)
- `accepted_values` on `is_confirmed_fast_food` (boolean only); spot-check that it's never `true` when `is_chain` is `false` isn't required (a brand can match with <3 locations in your slice), but worth a quick manual sanity check on row counts after the join

### Backlog note on this schema
Making `dim_restaurant` a proper **Type 2 SCD** (tracking name/address/cuisine changes over time with effective-dated rows) is a nice DE flex but not needed for the MVP's business questions — Type 1 (just overwrite) is fine since none of your MVP questions ask "what was this restaurant's cuisine tag 2 years ago." Mention Type 2 as a next step if asked in interviews.

---

## 6. Where ML Fits

- **Q1 is the only ML piece**: binary/multi-class classifier predicting B/C grade risk. Features: prior violation count, days since last inspection, critical violation history, cuisine, borough, score trend. Baseline logistic regression → then try XGBoost. Output: probability + feature importances, surfaced on Page 4.
- **Q2 is statistics, not ML** — keep it as a correlation calculation on weekly aggregates (already built into `mart_weekly_311_vs_inspection` above). Don't over-build it.

---

## 7. Dashboard Pages (Streamlit)

- **Page 1 — City & Borough Safety Overview:** 6 citywide KPI cards; borough filter + 6-way sort (safety rank, % Grade A, 311 rate, improvement rate, total restaurants, name) driving 4 borough cards; 100%-stacked grade-distribution bar chart; cuisine×borough heatmap with its own sort dropdown (rank / avg % Grade A / name); most-common-violations bar chart with a borough filter plus a frequency / critical-first / A–Z sort toggle.
- **Page 2 — Violations & 311 Correlation:** borough filter and an 8/12/26-week range toggle driving a dual-axis weekly line chart (311 complaints vs. critical violations) that auto-refreshes every few seconds with a new simulated week; a correlation-coefficient snapshot card; a geospatial overlap map (stylized NYC borough shapes with pulsing intensity markers) toggleable between Complaints / Failed Inspections / Overlap; and a sortable Borough Ranking table (click any column to sort).
- **Page 3 — SafeEats Restaurant Finder:** a "Recently Improved to Grade A" strip up top, then two sub-tabs. **Independent Restaurants** — search by name/ZIP plus borough, cuisine, grade, and flag (repeat-critical / recently-improved) filters, with a 7-way sort (name, grade, risk, score, days since inspection, cuisine, borough); each card shows a 3-year grade sparkline and opens a detail modal (score, risk %, full 3-year history chart, sample violation types, and a "View full risk analysis →" button that jumps to Page 4 with that restaurant pre-selected). **Fast Food Chains** — its own search/borough/cuisine/flag/sort controls; each chain collapses into one card showing a grade dot per location, and opens a modal listing every location's own grade with drill-in to that location's full detail modal.
- **Page 4 — Predictive Risk:** a restaurant selector and a borough filter for the risk list; a half-doughnut risk gauge with a color-coded status pill (High/Moderate/Low); a top-driving-factors list with a highest/lowest-impact sort toggle; and a Citywide Top-Risk Restaurants table with both a highest/lowest toggle and click-to-sort column headers.

---

## 8. Day-by-Day Plan (14 days, ~4–6 hrs/day)

| Day | Focus | Deliverable |
|---|---|---|
| 1 | Setup | GitHub repo, Docker Compose skeleton, S3 buckets (raw/bronze/silver/gold), pull sample data, explore DOHMH + 311 schemas, download the two static reference files, write scope doc |
| 2 | Ingestion | Python scripts: DOHMH incremental pull, 311 incremental pull (filtered), write raw JSON to S3 Bronze, add logging |
| 3 | Orchestration setup | Airflow via Docker Compose, DAG with 2 ingestion tasks, manual trigger test, audit log table (run_id, rows_ingested, timestamp) |
| 4 | Bronze → Silver (PySpark) | Dedupe inspections, standardize name/address, type casting, write partitioned Parquet |
| 5 | 311 Silver + geospatial join | Clean/filter 311 data, haversine join to nearest restaurant, write joined Silver table |
| 6 | dbt setup | Init dbt project, connect to Athena, staging models over Silver Parquet |
| 7 | dbt Gold — dims/facts | Build star schema (dims + facts above), name-normalization + chain-detection staging model (`dim_chain`, `is_chain`/`is_confirmed_fast_food`/`chain_key` on `dim_restaurant`, joined against the fast-food brand reference list), core dbt tests |
| 8 | dbt Gold — marts + reconciliation | Build 5 marts above, add source-to-target row count reconciliation check |
| 9 | ML | Feature engineering + train risk classifier on Gold data, save model artifact + feature importances |
| 10 | Full DAG + CI | Wire PySpark → geospatial join → dbt run → dbt test → reconciliation into one Airflow DAG; add GitHub Actions |
| 11 | Streamlit Page 1 & 2 | City/Borough overview + Violations/311 correlation, using the static GeoJSON for map shading |
| 12 | Streamlit Page 3 | Restaurant finder: Independent sub-section (search, grade history, consistency, days since inspection, nearby Grade A filter, map) + Fast Food Chains sub-section (aggregated chain cards from `mart_chain_summary`, drill-in to per-location grades) |
| 13 | Streamlit Page 4 + stretch | Risk gauge + feature importance table; "recently improved to A" list if not already done |
| 14 | Polish & deploy | README, architecture diagram, data dictionary, deploy (Streamlit Community Cloud), demo video, resume bullets |

---

## 9. Backlog / Phase 2 (documented, not built in 14 days)

- Multi-factor recommendation engine blending survey + hygiene + distance (Q3) — needs real survey data first
- Real (non-synthetic) survey collection via Google Forms
- Live "near my current location" map search with walking distance
- Late-night/24-7 open-now filtering — DOHMH has no real-time "open now" field; would need a separate live source (e.g. Google Places API)
- Dietary tag matching (vegan/halal/gluten-free) — not present in DOHMH data at all; would need a third-party join (Yelp/Google Places)
- Budget/price-tier filter — not present in DOHMH data
- Type 2 SCD on `dim_restaurant` (track historical name/address/cuisine changes)
