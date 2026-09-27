# Phase 4: Athena and dbt analytical warehouse

## Phase result

Phase 4 is complete for the current immutable Phase 3 snapshot.

The phase converted technical Silver Parquet data into a business-friendly
Gold warehouse that the future Streamlit dashboard can query through Amazon
Athena.

Verified result:

- Athena can read both Silver datasets from S3.
- dbt Core 1.12.3 and dbt-athena 1.11.0 connect successfully.
- Two staging views were created.
- Four reusable intermediate views were created.
- Six dimension tables were created.
- Two fact tables were created.
- Six dashboard marts were created.
- Fair-comparison metrics use consistent restaurant-count denominators.
- All 119 dbt tests passed.
- All 19 cross-layer reconciliation checks passed.

## The simplest mental model

```text
S3 Silver Parquet
        |
        v
Amazon Athena external tables
        |
        v
dbt staging views
        |
        v
dbt intermediate views
        |
        v
Gold dimensions and facts
        |
        v
Six dashboard marts
```

The tools have separate jobs:

- **S3** stores the Silver Parquet and physical Gold table data.
- **Athena** runs SQL over the files in S3.
- **AWS Glue Data Catalog** stores the table definitions used by Athena.
- **dbt** organizes the SQL into named models, builds them in dependency
  order, and tests the results.
- **Docker Compose** provides a repeatable container containing dbt and its
  Athena adapter.
- **Airflow** still schedules only Phase 2 Bronze ingestion. It does not yet
  run the Silver or Gold transformations automatically.

## Input snapshot

Phase 4 uses these successful Phase 3 outputs:

```text
Inspections Silver run:
inspections-silver-20260831-v1

311 Silver run:
complaints-silver-20260831-v1

Complaint/restaurant match run:
complaint-restaurant-matches-20260831-v1
```

The corresponding S3 inputs are:

```text
s3://safeeatsnyc-data-830460571487/silver/inspections/
    run_id=inspections-silver-20260831-v1/data/

s3://safeeatsnyc-data-830460571487/silver/complaint_restaurant_matches/
    run_id=complaint-restaurant-matches-20260831-v1/data/
```

Athena exposes them as:

```text
safeeats_silver.inspections
safeeats_silver.complaints
```

Gold views and tables are created in:

```text
safeeats_gold
```

Their physical table data is stored under:

```text
s3://safeeatsnyc-data-830460571487/gold/
```

## Files added for Phase 4

### Athena setup

`warehouse/setup_athena.py`

- Creates the `safeeats_silver` and `safeeats_gold` databases.
- Registers the current inspection and complaint Parquet locations.
- Defines the Silver field types for Athena.
- discovers the year and month partitions using `MSCK REPAIR TABLE`.

### dbt Docker environment

`warehouse/Dockerfile`

- Builds a small Python 3.13 dbt image.
- Installs Git because dbt checks for it.
- Keeps build tools out of the final image.

`warehouse/requirements.txt`

- Installs dbt Core 1.12.x.
- Installs dbt-athena 1.11.x.
- Installs the AWS CRT dependency required by the local AWS login profile.

`docker-compose.yml`

- Defines the optional `dbt` service under the `warehouse` profile.
- Mounts `dbt/` into `/usr/app`.
- mounts the reviewed `data/reference/` CSV files as dbt seeds.
- Mounts the existing AWS profile and writable login-token cache.
- Passes the S3, Athena, region, and profile configuration into the container.

### dbt configuration

`dbt/profiles.yml`

- Connects dbt to Athena through the `primary` workgroup.
- Uses `awsdatacatalog` and the `safeeats_gold` schema.
- Sends query results, temporary tables, and Gold data to separate S3 paths.

`dbt/dbt_project.yml`

- Makes staging and intermediate models views.
- Makes dimensions, facts, and marts physical tables.
- Defines the seed location and preserves ZIP codes as strings.

## Step 1: Register Silver data in Athena

The setup script creates Athena metadata. It does not copy the Silver data;
Athena reads the existing Parquet directly from S3.

```powershell
python warehouse/setup_athena.py `
  --inspections-run-id inspections-silver-20260831-v1 `
  --matches-run-id complaint-restaurant-matches-20260831-v1
```

Verified Silver counts:

| Athena table | Rows |
|---|---:|
| `safeeats_silver.inspections` | 247,714 |
| `safeeats_silver.complaints` | 150,231 |

## Step 2: Build and verify dbt

Build the dbt image only after changing `warehouse/Dockerfile` or
`warehouse/requirements.txt`:

```powershell
docker-compose --profile warehouse build dbt
```

Verify the installed versions:

```powershell
docker-compose --profile warehouse run --rm dbt --version
```

Verified versions:

```text
dbt-core:   1.12.3
dbt-athena: 1.11.0
```

Check configuration and AWS/Athena access:

```powershell
docker-compose --profile warehouse run --rm dbt debug --profiles-dir .
```

Check the project structure without creating tables:

```powershell
docker-compose --profile warehouse run --rm dbt parse --profiles-dir .
```

SQL-only changes do not require a Docker rebuild because the local `dbt/`
folder is mounted into the container.

## Step 3: Create the staging views

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select path:models/staging `
  --profiles-dir .
```

This created:

- `stg_inspections`
- `stg_complaints`

### What `stg_inspections` changes

- Trims restaurant name, borough, address, ZIP, and cuisine text.
- Converts empty versions of those fields to null.
- Converts missing fast-food and co-brand flags to `false`.
- Converts grades to uppercase.
- Gives selected columns clearer business names.
- Preserves the types already created in Silver.

It does not re-run name normalization and does not calculate complex metrics.

### What `stg_complaints` changes

- Renames `unique_key` to `complaint_id`.
- Selects the fields required by the analytical warehouse.
- Preserves matched and unmatched complaints.
- Preserves the Silver data types.

Initial staging validation:

```powershell
docker-compose --profile warehouse run --rm dbt test `
  --select path:models/staging `
  --profiles-dir .
```

Result: all 10 staging tests passed.

## Step 4: Create the restaurant and chain preparation views

Load the Phase 1 ZIP-to-neighborhood reference:

```powershell
docker-compose --profile warehouse run --rm dbt seed `
  --select zip_to_nta `
  --profiles-dir .
```

The seed contains 221 ZIP-to-NTA rows. ZIP codes remain strings so leading
zeros are not lost.

Build the restaurant preparation views:

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select path:models/intermediate `
  --profiles-dir .
```

This initially creates:

- `stg_restaurant_current`: one deterministic current row per DOHMH `CAMIS`.
- `stg_chain_flags`: location counts and chain classification.

`CAMIS` is the DOHMH restaurant identifier. Selecting one row per `CAMIS`
prevents the restaurant dimension from repeating for every inspection and
violation.

## Step 5: Classify chains without changing Phase 1 brands

The two classifications are deliberately independent.

### `is_chain`

```text
Group current restaurants by restaurant_name_normalized
        |
        v
Count distinct CAMIS locations
        |
        +-- 3 or more --> is_chain = true
        `-- fewer than 3 --> is_chain = false
```

This identifies any repeated-location group, including local chains that are
not fast food.

### `is_confirmed_fast_food`

This value is not guessed again in dbt. Phase 1 defined the reviewed alias and
co-brand rules, and Phase 3 applied those exact rules to the DOHMH names.

dbt preserves:

- `restaurant_name_normalized`
- `is_confirmed_fast_food`
- `is_reviewed_co_brand`
- `fast_food_brand_names`

A co-branded location therefore remains one restaurant row while retaining
all confirmed constituent brands in its brand array. Its composite restaurant
name is not silently replaced with only one brand.

## Step 6: Create the star schema

Build the dimensions:

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select path:models/dimensions `
  --profiles-dir .
```

Build the facts:

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select path:models/facts `
  --profiles-dir .
```

### Dimension tables

| Table | Rows | Grain and purpose |
|---|---:|---|
| `dim_restaurant` | 27,220 | One current Type 1 row per CAMIS |
| `dim_chain` | 705 | One row per normalized name with at least three locations |
| `dim_borough` | 5 | One row per NYC borough |
| `dim_date` | 1,097 | One row per calendar day in the data range |
| `dim_violation` | 113 | One row per non-null violation code |
| `dim_complaint_type` | 3 | One row per relevant 311 complaint category |

`dim_restaurant` also joins the ZIP/NTA seed and contains cuisine, location,
chain, confirmed-fast-food, and reviewed co-brand fields.

Restaurant, chain, violation, and complaint-type keys are deterministic SHA-256
keys. The same source value therefore receives the same key on later builds.

### Fact tables

| Table | Rows | Grain |
|---|---:|---|
| `fact_inspection` | 247,714 | One row per deduplicated inspection/violation source record |
| `fact_311_complaint` | 150,231 | One row per unique complaint |

`fact_inspection` preserves legitimate multiple violations from the same
inspection. Its `inspection_id` groups rows belonging to the same inspection
event, while `inspection_event_key` remains unique per source row.

`fact_311_complaint.restaurant_key` is intentionally nullable. It remains null
when Phase 3 did not find a restaurant within 100 metres or the complaint had
no valid coordinates.

The Gold layer retains the grade supplied by DOHMH. It does not manufacture a
grade from the numeric score because official grading can involve more context
than a simple score range.

## Step 7: Prepare inspection-level calculations

An inspection can have several valid violation rows. Counting fact rows as
inspections would therefore inflate inspection totals and repeat grades.

These reusable views prevent that mistake:

- `int_inspection_events`: one row per inspection ID.
- `int_latest_graded_inspection`: latest A, B, or C event per restaurant.

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select int_inspection_events int_latest_graded_inspection `
  --profiles-dir .
```

The current snapshot contains 78,353 distinct inspection events.

## Step 8: Create the six dashboard marts

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select path:models/marts `
  --profiles-dir .
```

| Mart | Rows | Dashboard-ready result |
|---|---:|---|
| `mart_borough_grade_summary` | 18 | A/B/C distribution for five boroughs and citywide |
| `mart_cuisine_borough_heatmap` | 362 | Grade A results by cuisine and borough |
| `mart_violation_by_borough` | 477 | Violation frequency by borough and criticality |
| `mart_weekly_311_vs_inspection` | 942 | Weekly complaints versus critical violations for boroughs and citywide |
| `mart_restaurant_grade_history` | 42,826 | Per-restaurant graded inspection timeline |
| `mart_chain_summary` | 705 | One summary row per detected chain |

### Fair-comparison metrics

Raw totals alone can unfairly make a borough with more restaurants look worse.
The marts therefore retain the raw counts and calculate normalized values.

The shared pattern is:

```text
normalized rate = event count / total restaurants * 100
```

Examples include:

- restaurants at each grade per 100 restaurants;
- Grade A restaurants per 100 restaurants for a cuisine/borough combination;
- violations per 100 restaurants;
- complaints per 100 restaurants;
- critical violations per 100 restaurants.

`dim_borough.total_restaurants` is the shared denominator for borough metrics,
so different dashboard pages do not calculate the same KPI differently.

The grade-distribution percentage uses graded restaurants as its denominator.
The mart separately keeps total restaurants so users can distinguish grade
distribution from coverage.

## Step 9: Run the complete dbt test suite

```powershell
docker-compose --profile warehouse run --rm dbt test `
  --profiles-dir .
```

Verified result:

```text
PASS=119 WARN=0 ERROR=0 SKIP=0 TOTAL=119
```

The tests cover:

- unique primary and natural keys;
- required non-null values;
- accepted A/B/C grades in graded marts;
- valid boolean values;
- fact-to-dimension foreign keys;
- complaint-to-restaurant nullable relationships;
- restaurant-to-chain relationships;
- the three-location chain rule;
- preservation of Phase 1 fast-food and co-brand results;
- Silver, staging, and fact row-count equality;
- normalized-rate formulas;
- grade percentage ranges and totals;
- chain location-count totals;
- exactly one latest graded row per restaurant.

### Problems fixed during testing

1. The fast-food boolean test originally compared an Athena boolean with the
   strings `True` and `False`. Setting `quote: false` made the test use real
   boolean literals.
2. Athena initially inferred `dim_date.calendar_date` as `timestamp(0)`, which
   conflicted with its millisecond timestamp configuration. Explicitly casting
   the column to `date` fixed the problem.
3. The Athena workgroup was corrected to the existing `primary` workgroup.
4. Git and the AWS CRT dependency were added to the dbt Docker image so `dbt
   debug` and the existing AWS login profile work inside the container.

## Step 10: Reconcile every layer

Run the repeatable reconciliation program:

```powershell
python warehouse/reconcile_phase4.py `
  --inspections-run-id inspections-silver-20260831-v1 `
  --complaints-run-id complaints-silver-20260831-v1 `
  --matches-run-id complaint-restaurant-matches-20260831-v1
```

It reads three sources of evidence:

```text
Phase 2 SQLite ingestion audit
            +
Phase 3 quality_report.json files in S3
            +
Phase 4 Athena table counts
            |
            v
19 explicit reconciliation checks
```

Verified result:

```text
status:        SUCCESS
checks passed: 19
checks failed: 0
```

### Inspection reconciliation

```text
250,379 selected Bronze rows
  - 2,665 exact overlap duplicates
  -     0 rejected rows
= 247,714 Silver rows
= 247,714 staging rows
= 247,714 fact rows
```

The 247,714 fact rows do not represent 247,714 separate inspections. They are
inspection/violation records. Grouping related rows produces 78,353 inspection
events for inspection-level metrics.

### Complaint reconciliation

```text
151,170 selected Bronze rows
  -   939 repeated complaint IDs from overlapping runs
  -     0 rejected rows
= 150,231 Silver complaints
= 150,231 staging rows
= 150,231 fact rows
```

Both matched and unmatched complaints remain in the fact table.

### Why dimensions and marts have different counts

This is expected and is not data loss:

- `dim_restaurant` collapses many inspection rows into one CAMIS row.
- `dim_chain` contains only normalized names seen at three or more locations.
- `dim_violation` contains one row per violation code.
- grade history contains only A, B, and C inspection events.
- summary marts aggregate many facts into each chart-ready row.

### Reconciliation outputs

The command overwrites the latest reports at:

```text
data/audit/phase4_reconciliation.json
docs/project_documents/phase4_reconciliation.md
s3://safeeatsnyc-data-830460571487/gold/_audit/
    phase4_reconciliation/latest.json
```

The fixed `latest.json` key avoids creating a new visible audit filename for
every execution. If S3 bucket versioning is enabled, AWS may still retain older
object versions for recovery.

## Phase 4 validation snapshot

At the original Phase 4 validation, the Gold tables fully reconciled with the
August 31 Silver snapshot. The ingestion audit also contained newer successful
Bronze data:

- 3,441 DOHMH inspection rows from September 5;
- 1,108 relevant 311 complaint rows from September 5.

These rows are not lost. They arrived after the Silver snapshot used by Athena
and are waiting for the next Silver and Gold refresh.

Phase 6 later connected Bronze, Silver, Athena, dbt, tests, and reconciliation
in the daily Airflow DAG. The dashboard now reports the latest completed
warehouse snapshot rather than assuming this historical validation date is
current.

## Normal operating commands

After AWS authentication and with the current Silver tables already registered,
the normal Gold rebuild is:

```powershell
docker-compose --profile warehouse run --rm dbt seed `
  --select zip_to_nta `
  --profiles-dir .

docker-compose --profile warehouse run --rm dbt run `
  --profiles-dir .

docker-compose --profile warehouse run --rm dbt test `
  --profiles-dir .

python warehouse/reconcile_phase4.py `
  --inspections-run-id inspections-silver-20260831-v1 `
  --complaints-run-id complaints-silver-20260831-v1 `
  --matches-run-id complaint-restaurant-matches-20260831-v1
```

`dbt run` automatically follows model dependencies. The earlier individual
commands remain useful while learning or troubleshooting a particular layer.

## Important limitations

- Phase 4 is attached to explicitly selected immutable Silver run IDs.
- New Bronze data does not enter Gold until Silver and Gold are rebuilt.
- The current restaurant dimension is Type 1: one current row per CAMIS. It
  does not retain effective-dated restaurant attribute changes.
- The three-location chain threshold is a documented heuristic, not proof of
  common ownership.
- Confirmed fast food is based on the reviewed Phase 1 reference policy and is
  independent of `is_chain`.
- A complaint/restaurant match indicates proximity within 100 metres, not
  proof that the restaurant caused the complaint.
- Weekly correlation describes association and does not establish causation.
- Gold can remain behind Bronze when a daily run is incomplete or fails.
  Snapshot metadata and reconciliation make that delay visible.

## Completion checklist

- [x] Athena reads Silver Parquet from S3.
- [x] dbt connects to Athena.
- [x] Staging views are available.
- [x] Six dimensions are available.
- [x] Two facts are available.
- [x] Chain and confirmed-fast-food classifications remain independent.
- [x] Reviewed co-brand arrays are preserved.Phase 4 fact/dimension tables
            ↓
ml_graded_inspections
42,824 graded res
- [x] Six dashboard marts are available.
- [x] Raw totals and normalized metrics are both available.
- [x] All 119 dbt tests pass.
- [x] All 19 reconciliation checks pass.
- [x] Every expected row-count difference is documented.
