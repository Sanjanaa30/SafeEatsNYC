# Data quality, assumptions, and limitations

## Purpose

This document gathers the project's main data-quality findings, assumptions,
controls, and remaining limitations in one place.

Detailed evidence remains in the individual phase guides.

## Quality approach

SafeEats NYC does not assume that a successful API request produces
analysis-ready data. Quality checks occur at every layer:

~~~text
Source validation
    |
    v
Bronze request and audit records
    |
    v
Silver schema, cleaning, deduplication, and read-back checks
    |
    v
dbt constraints and relationship tests
    |
    v
Bronze-to-Silver-to-Gold reconciliation
    |
    v
Model backtesting, calibration, subgroup, and drift checks
    |
    v
API response validation and safe dashboard fallbacks
~~~

## Core assumptions

- CAMIS is the natural DOHMH restaurant identifier.
- A 311 unique key identifies one complaint.
- Bronze should preserve source responses without cleaning them.
- January 1, 1900 is treated as a not-yet-inspected sentinel rather than a
  normal inspection date.
- Current grade metrics use A, B, and C unless a metric explicitly states
  otherwise.
- The current restaurant dimension keeps one current row per CAMIS.
- A restaurant group needs a high-confidence name relationship and enough
  distinct locations under the current grouping policy.
- Fast-food confirmation is separate from restaurant-group detection.
- A complaint can be geographically matched only when it has valid coordinates.
- The nearest eligible restaurant within 100 meters is a proximity match, not
  proof of responsibility.
- Weekly correlations are descriptive relationships, not causal evidence.
- Predictive risk estimates a possible future B/C grade, not illness, closure,
  or a particular violation.

## Known issues and controls

### Changing source data

**Issue:** NYC Open Data changes as records are added or corrected.

**Effect:** A long paginated download is not a perfect transactional snapshot.

**Current control:**

- ordered pagination
- recorded request windows
- immutable Bronze pages
- a two-day incremental overlap
- Silver deduplication
- periodic reconciliation

**Remaining limitation:** A correction with an old unchanged source timestamp
can fall outside the overlap. Periodic wider backfills may still be needed.

### Duplicate records

**Issue:** Incremental overlap and source updates can create repeated records.

**Current control:**

- Bronze intentionally keeps every downloaded page
- Silver removes exact inspection duplicates without collapsing legitimate
  violation rows
- duplicate complaint IDs keep the newest version
- output and read-back counts are written to quality reports

**Remaining limitation:** A source correction can look like a legitimate new
version and must be resolved using the documented business key and ordering.

### Inspection grain

**Issue:** One inspection may contain several violation rows.

**Effect:** Counting source rows as inspections would overstate inspection
activity and distort rates.

**Current control:** Gold creates a shared inspection ID and a separate
inspection-event model. Dashboard inspection metrics use the event grain.

### Missing or unusual grades

**Issue:** Source grades can be blank or contain values such as N, P, or Z.

**Current control:**

- Silver preserves source grade values
- current grade distributions use documented A/B/C rules
- the model uses mature A/B/C outcomes and excludes incomplete labels

**Remaining limitation:** Restaurants without enough graded history cannot
receive a current model score.

### Missing or invalid coordinates

**Issue:** Some restaurants or complaints have missing, zero, or invalid
coordinates.

**Current control:**

- coordinate values are typed and validated
- coordinate quality receives an explicit status
- coordinate-less complaints remain in the dataset
- only valid points enter geographic matching

**Remaining limitation:** Complaints without valid coordinates cannot be linked
geographically.

### Geographic complaint matching

**Issue:** A nearby complaint may not refer to the nearest restaurant.

**Current control:**

- only the nearest eligible restaurant within 100 meters is matched
- distance and match status remain visible in the data
- unmatched complaints remain available
- dashboard wording describes proximity rather than responsibility

**Remaining limitations:**

- matching uses the restaurant's latest valid location rather than a complete
  historical address for every complaint date
- the 100-meter threshold is an MVP policy and should be validated with a
  larger manually labelled sample before enforcement or causal use

### Restaurant names and groups

**Issue:** Punctuation, store numbers, spelling changes, location suffixes, and
co-brands make name grouping difficult. Similar names may also belong to
unrelated businesses.

**Current control:**

- the original DOHMH name is preserved
- a separate normalized name is used for matching
- aliases and co-brand associations require review
- exact or short same-cuisine variants can extend established multi-location
  groups
- group method and confidence are retained
- uncertain candidates remain in review queues

**Remaining limitations:**

- group membership is a documented heuristic, not proof of common ownership
- new naming patterns may require new reviewed aliases
- a restaurant can change name or ownership while keeping the same CAMIS

### Brand classification

**Issue:** OpenStreetMap brand tags are incomplete and can classify cafes,
dessert shops, or non-restaurants inconsistently.

**Current control:** Reviewed INCLUDE and EXCLUDE overrides document manual
decisions.

**Remaining limitation:** Brand coverage depends on OpenStreetMap and the
current review policy.

### ZIP and neighborhood assignment

**Issue:** ZIP/ZCTA and Neighborhood Tabulation Area boundaries are not
one-to-one.

**Current control:** Each ZIP is assigned to the NTA with the largest polygon
overlap.

**Remaining limitation:** The resulting neighborhood is a practical label, not
an exact point-in-polygon address result.

### Borough and cuisine comparisons

**Issue:** Raw totals are strongly affected by the number of restaurants and
inspections in each group.

**Current control:** The dashboard uses rates such as findings per 100
restaurants, complaints per 1,000 restaurants, or affected inspections per 100
inspections.

**Remaining limitation:** A rate can be unstable for a small group. Counts and
the selected time period should be considered with the rate.

### Correlation analysis

**Issue:** Correlation values can change with complaint type, time range, lag,
and weekly variation.

**Current control:**

- users can see and change the selected period and delay
- the interface shows paired-week counts
- labels use three transparent strength bands
- negative values are described as opposite movement

Current display bands:

| Absolute score | Label |
|---|---|
| 0.00 to 0.29 | Weak |
| 0.30 to 0.59 | Moderate |
| 0.60 to 1.00 | Strong |

**Remaining limitations:**

- changing thresholds changes wording, not the underlying relationship
- a stronger relationship still does not prove causation
- a small number of weekly pairs gives weaker evidence

### Predictive model

**Issue:** B/C outcomes are less common than A outcomes, recent labels need time
to mature, and model quality can change.

**Current control:**

- chronological rather than random evaluation
- strict past-only feature boundaries
- logistic-regression baseline retained for comparison
- XGBoost evaluated with precision, recall, F1, ROC-AUC, average precision, and
  calibration
- probability calibration
- a 45-day outcome-maturity delay in scheduled refreshes
- subgroup and score-distribution monitoring
- hard quality gates before promotion
- model version and scoring time stored with results

**Remaining limitations:**

- a score is a probability, not a guarantee
- factor contributions describe model influence, not cause
- XGBoost is less transparent than logistic regression
- restaurants without sufficient graded history are not scored
- performance can drift as inspection policy and restaurant behavior change

### Freshness

**Issue:** Bronze, Silver, Gold, and model outputs do not refresh at exactly the
same moment.

**Current control:**

- immutable run IDs
- explicit snapshot metadata
- a daily data DAG
- a monthly model DAG
- a promoted score pointer
- freshness information in the website header and API metadata

**Remaining limitation:** The dashboard is a completed warehouse snapshot, not
a live view of the NYC APIs.

### Local runtime

**Issue:** The current orchestration environment runs on one local computer.

**Current control:** Docker Compose provides repeatable service definitions and
Airflow supplies retries and task-state history.

**Remaining limitations:**

- Docker Desktop must be running for schedules to execute
- the computer must be awake and online
- AWS login sessions can expire
- SQLite audit storage is appropriate for one local worker, not a distributed
  multi-machine environment

## Tests and monitoring

| Layer | Main checks |
|---|---|
| Ingestion | Required fields, pagination, retry behavior, audit records, and idempotency |
| Silver | Schema casts, deduplication, geographic thresholds, counts, and Parquet read-back |
| Gold | Not-null, unique, accepted-value, relationship, custom business-rule, and reconciliation tests |
| Model | Chronological backtests, leakage checks, precision, recall, F1, ROC-AUC, calibration, subgroup checks, and drift checks |
| API | Input validation, response schemas, safe errors, search, and service behavior |
| Frontend | Correlation helpers, linting, and TypeScript checks |

## Data not available from the selected sources

SafeEats NYC does not claim to provide:

- menu prices
- opening hours or open-now status
- dietary or allergen guarantees
- customer ratings
- survey-based recommendations
- walking or driving routes
- ownership proof from similar restaurant names
- proof that a restaurant caused a 311 complaint

## Reporting a new quality issue

When a new issue is found:

1. Record the source row or restaurant ID.
2. Identify the affected layer and grain.
3. Decide whether the source is wrong, the business rule is incomplete, or the
   display is misleading.
4. Add a small reproducible test.
5. Correct the earliest appropriate layer.
6. Rebuild downstream outputs.
7. Update this document if the limitation remains.

## Related documents

- [Architecture](architecture.md)
- [Data dictionary](data_dictionary.md)
- [Scope and assumptions](phase1_scope.md)
- [Silver processing](phase3_silver.md)
- [Warehouse reconciliation](phase4_reconciliation.md)
- [Predictive model](phase5_predictive_model.md)
