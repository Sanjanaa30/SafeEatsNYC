# Phase 5: Predictive restaurant-risk model

## Phase result

Phase 5 is functionally complete for the current Phase 3 and Phase 4 snapshot.

The phase created a model that estimates the probability that a restaurant's
next graded inspection will receive a **B or C** instead of an **A**.

Verified result:

- Historical graded inspections were converted into 18,432 prediction examples.
- Every feature uses information from before the inspection being predicted.
- Training and testing were split by time instead of randomly.
- Logistic regression was trained as the explainable baseline.
- The baseline was tuned and its probabilities were calibrated.
- August 2026 was identified as an incomplete, or immature, label period.
- XGBoost was compared with logistic regression on the same mature test period.
- XGBoost was selected using precision, recall, F1, ROC-AUC, and calibration.
- The selected model was retrained using 17,596 mature historical examples.
- Current risk scores were produced for 24,392 eligible restaurants.
- The final model and scores were saved and read back successfully from S3.

## The simplest mental model

```text
Phase 4 inspection and complaint tables in Athena
                         |
                         v
           One row per graded restaurant-day
                         |
                         v
       Previous inspection ---> next inspection grade
               |                       |
               |                       `--> answer: A or B/C
               v
        Past-only model features
                         |
                         v
       Older rows for training / newer rows for testing
                         |
                         v
        Logistic regression compared with XGBoost
                         |
                         v
                  XGBoost selected
                         |
                         v
          Retrain on all mature historical rows
                         |
                         v
        Score the latest state of current restaurants
                         |
                         v
             S3 current-risk Parquet output
```

## What each tool does

- **S3** stores prepared matrices, models, reports, predictions, and current
  restaurant risk scores.
- **Athena** lets Python and dbt query the Phase 4 Gold tables stored in S3.
- **dbt** creates the historical training feature tables and the latest feature
  row for each current restaurant.
- **Docker Compose** runs a repeatable Python modeling environment containing
  pandas, scikit-learn, XGBoost, and PyArrow.
- **scikit-learn** performs missing-value handling, encoding, logistic
  regression, calibration, and evaluation.
- **XGBoost** provides the second, nonlinear model used in the final comparison.
- **PyArrow** writes current restaurant scores as Parquet.
- **Airflow** refreshes the dbt ML feature tables as part of the Phase 6 Gold
  build. Final XGBoost retraining, model promotion, and score-file generation
  remain a deliberate manual workflow through Docker Compose.

## Input data

Phase 5 starts from the Phase 4 Gold warehouse in Athena:

```text
safeeats_gold.fact_inspection
safeeats_gold.stg_inspections
safeeats_gold.stg_complaints
safeeats_gold.dim_restaurant
safeeats_gold.dim_borough
safeeats_gold.dim_date
```

Those tables ultimately come from the immutable Phase 3 Silver runs:

```text
Inspections: inspections-silver-20260831-v1
Complaints:  complaints-silver-20260831-v1
Matches:     complaint-restaurant-matches-20260831-v1
```

Phase 5 therefore reflects the Gold snapshot built from data available through
that Silver build. New Bronze ingestion does not automatically change the model
until Silver, Gold, and Phase 5 are rebuilt in order.

## Important terms

### Prediction anchor

The prediction anchor is the last graded inspection whose result is already
known when creating the model features.

Example:

```text
April 2, 2024 inspection: Grade A, score 8
                         ^
                         prediction anchor
```

### Target inspection

The target is the restaurant's next graded inspection after the anchor.

```text
April 2, 2024: Grade A  --->  August 13, 2026: Grade C
previous known result        target being predicted
```

### Label

The label is the answer the model learns to predict:

```text
Next grade A   = 0
Next grade B/C = 1
```

The example above receives label `1` because the next grade was C.

### Feature

A feature is information supplied to the model. Examples include previous
score, prior violations, borough, cuisine, and recent nearby complaints.

### Data leakage

Data leakage occurs when the model receives information that would not have
been known at prediction time.

For example, using the target inspection's score would reveal much of the
answer. Phase 5 explicitly excludes the target grade, target score, target
violations, target identifiers, and later complaint information from the model
matrix.

### Class imbalance

Only a small percentage of examples receive B or C. A model could achieve high
accuracy by predicting A almost every time, while being useless for safety-risk
detection. This is why precision, recall, F1, ROC-AUC, and calibration are used
instead of relying on accuracy alone.

### Precision

Of the restaurants flagged as risky, precision measures how many actually
received B or C.

```text
100 restaurants flagged
30 actually receive B/C
Precision = 30%
```

### Recall

Of all restaurants that actually received B or C, recall measures how many the
model successfully flagged.

```text
100 restaurants actually receive B/C
77 were flagged Moderate or High
Recall = 77%
```

### F1 score

F1 combines precision and recall. It is helpful when one model has higher
precision but another has higher recall.

### ROC-AUC

ROC-AUC measures how well the model ranks risky outcomes above safer outcomes
across every possible threshold.

- `0.50` means no useful ranking ability.
- `1.00` means perfect ranking.
- The selected model achieved approximately `0.757`.

### Probability calibration

Calibration asks whether the predicted probabilities resemble real outcome
rates. If a group receives an average prediction of 10%, roughly 10% of that
group should receive B or C.

The Brier score measures probability error. Lower is better.

### Label maturation

A recent inspection may not yet have its final grade. Grade A can be recorded
quickly, while unsuccessful initial inspections may remain blank, N, or Z until
later processing or reinspection. Evaluating those recent records too early
creates a misleadingly low B/C rate.

## Phase 5 files

### dbt feature models

`dbt/models/ml/ml_graded_inspections.sql`

- Produces one row per restaurant and graded inspection date.
- Preserves legitimate violation counts.
- Combines the two reviewed same-restaurant, same-day duplicate event pairs.

`dbt/models/ml/ml_inspection_targets.sql`

- Orders graded inspections separately for each restaurant.
- Connects each known inspection to its strictly later next graded inspection.
- Creates the `target_is_bc` label.

`dbt/models/ml/ml_training_features.sql`

- Builds past-only historical inspection features.
- Counts matched nearby complaints only from the previous 90 days.
- Produces one feature row for each labelled target.

`dbt/models/ml/ml_current_features.sql`

- Selects the latest graded history for each eligible current restaurant.
- Calculates complaint features relative to the scoring date.
- Produces the rows used for current risk scoring.

`dbt/models/ml/ml.yml`

- Documents the four ML tables.
- Tests keys, relationships, grades, dates, and required fields.

### Python modeling code

`ml/prepare_training_data.py`

- Reads `safeeats_gold.ml_training_features` from Athena.
- Applies the predictor allow-list.
- Splits rows chronologically.
- Fits missing-value and encoding logic using training rows only.
- Writes prepared matrices and their metadata to S3.

`ml/verify_prepared_data.py`

- Reads the matrices back from S3.
- Confirms dimensions, target counts, feature names, and missing values.

`ml/train_logistic_regression.py`

- Trains the first logistic-regression baseline.
- Evaluates its discrimination, classification, and calibration.
- Saves the baseline model and report.

`ml/tune_calibrate_logistic.py`

- Tunes logistic regression using chronological cross-validation.
- Uses separate training periods for calibration and threshold selection.
- Excludes immature August outcomes from final metrics.

`ml/compare_xgboost.py`

- Tests eight small XGBoost configurations.
- Calibrates XGBoost using the same time windows as logistic regression.
- Compares both models using the same mature test rows.
- Records the final selection decision.

`ml/calibration.py`

- Contains the stable, reusable probability-calibration class stored inside
  the final model bundle.

`ml/retrain_and_score.py`

- Retrains the selected XGBoost model on all mature labelled history.
- Builds out-of-fold probabilities for final calibration.
- Scores current eligible restaurants.
- Calculates each restaurant's main contributing risk factors.
- Writes the final model and dashboard-ready scores to S3.

`ml/verify_logistic_model.py`

- Confirms a saved logistic model and its prediction file can be reloaded.

`ml/verify_final_outputs.py`

- Reloads the final XGBoost bundle.
- Reads the current score Parquet.
- Validates required columns, row uniqueness, probability bounds, risk
  categories, contributing factors, timestamps, and model version.

### Docker files

`ml/Dockerfile`

- Creates the dedicated Phase 5 Python image.

`ml/requirements.txt`

- Installs pandas, NumPy, scipy, scikit-learn, XGBoost, PyArrow, boto3,
  joblib, and pytest.

`docker-compose.yml`

- Defines the optional `ml` service under the `modeling` profile.
- Mounts the project and the existing AWS profile into the container.
- Passes the S3 bucket, AWS region, and Athena settings to the job.

## Step 1: Build one row per graded restaurant-day

The raw inspection fact is at violation-row grain. Multiple violations from
one inspection are legitimate and cannot simply be deleted.

The first ML model groups those rows carefully into one graded
restaurant-date:

```text
Restaurant A, June 1, violation 02B --+
Restaurant A, June 1, violation 04L --+--> one graded restaurant-day
Restaurant A, June 1, violation 06C --+    violation_count = 3
```

Result:

| Measurement | Result |
|---|---:|
| Graded restaurant-days | 42,824 |
| Restaurants with graded history | 24,392 |
| First graded inspection date | August 30, 2023 |
| Latest grade date in snapshot | August 25, 2026 |

## Step 2: Create the next-inspection label

Each graded restaurant-day is connected to the next graded day for the same
restaurant.

The latest known grade for each restaurant has no later answer, so it cannot
be a labelled training example.

```text
42,824 graded restaurant-days
-24,392 final observations with no later known grade
=18,432 labelled examples
```

Label result:

| Outcome | Rows |
|---|---:|
| Next grade A | 16,618 |
| Next grade B/C | 1,814 |
| Total | 18,432 |
| Overall B/C rate | 9.84% |

## Step 3: Build past-only features

The feature table contains:

- Previous grade and score
- Earlier grade and score
- Recent score change
- Days since the previous graded inspection
- Previous violation and critical-violation counts
- Number of previously known graded inspections
- Historical violation totals
- Historical A, B, and C counts
- Historical Grade A rate
- Historical grade consistency
- Cuisine and borough
- Matched nearby 311 complaint counts from the previous 90 days

The target inspection's score and violations are not present as predictors.

Result:

- 18,432 feature rows
- 18,432 target rows
- No missing previous scores
- 18 missing borough names retained for later handling
- 3,633 examples with at least one earlier nearby complaint

## Step 4: Enforce the leakage boundary

Python uses an explicit allow-list of model features. The following fields are
kept only for audit, splitting, or as the answer and are not placed in `X`:

```text
restaurant identifiers
prediction anchor identifier and date
target inspection identifier and date
target grade
target_is_bc answer
latitude and longitude
```

`target_is_bc` becomes `y`, the answer vector. It is not included in the
predictor matrix.

## Step 5: Prepare values for machine learning

Numeric missing values are replaced with the median learned from the training
period. Numeric features are then scaled.

Example:

```text
Earlier score: missing
Training-period median earlier score: 12
Prepared earlier score: 12
```

Categorical fields use `UNKNOWN` for missing values and one-hot encoding.

Example:

```text
Previous grade = B

previous_grade_A = 0
previous_grade_B = 1
previous_grade_C = 0
```

The 22 readable input predictors became 114 encoded model columns.

Missing values before preparation:

- Earlier score and score trend: 15,163 rows. This is expected when a
  restaurant does not yet have two earlier graded inspections.
- Borough name: 18 rows.

Missing values after preparation: **0**.

## Step 6: Split by time

The split is chronological:

```text
Training targets: December 19, 2023 through April 30, 2026
Test targets:     May 1, 2026 through August 25, 2026
```

| Split | Rows | B/C rows | B/C rate |
|---|---:|---:|---:|
| Training | 14,811 | 1,601 | 10.81% |
| Initial test | 3,621 | 213 | 5.88% |

No random split was used. This better represents predicting future outcomes
from older history.

## Step 7: Train the explainable baseline

Logistic regression was used first because it is simple, fast, and provides a
coefficient for each encoded feature.

The normal probability threshold of 50% was not suitable:

- Precision: 37.50%
- Recall: 4.23%
- F1: 7.59%

Only 9 of 213 initial test B/C outcomes were found at that threshold. This is
why risk thresholds must be chosen for this imbalanced safety problem rather
than accepting 50% automatically.

## Step 8: Investigate the unusual August result

The August 2026 Silver snapshot contained:

| Grade state | Inspection events |
|---|---:|
| A | 995 |
| B | 2 |
| C | 1 |
| N | 184 |
| Z | 201 |
| Blank | 882 |

The N, Z, and blank inspections also had much higher average scores than the
Grade A inspections. This indicates incomplete grade processing, not a sudden
improvement in safety.

The ML target code did not convert those records to A. However, the few grades
that had matured were overwhelmingly A, which biased the newest evaluation
period.

Decision:

- Keep the August records for traceability.
- Mark 836 August target examples as immature.
- Exclude them from evaluation and final retraining.
- Use May through July 2026 as the mature final test period.

## Step 9: Tune and calibrate logistic regression

The original training period was divided again without using the final test:

| Period role | Rows | Purpose |
|---|---:|---|
| Development | 10,718 | Tune and fit the base model |
| Calibration | 1,732 | Correct probability scale |
| Threshold validation | 2,361 | Choose Low/Moderate/High boundaries |
| Mature final test | 2,785 | Final evaluation only |

Eight logistic configurations were evaluated with four chronological folds.
The best was:

```text
C = 0.01
class_weight = None
```

`C = 0.01` means stronger regularization. Regularization discourages very large
coefficients and helps the model generalize.

Sigmoid calibration improved the Brier score from `0.0658` to `0.0640` and
moved the mean predicted risk closer to the observed rate.

## Step 10: Compare logistic regression with XGBoost

XGBoost can learn nonlinear relationships and feature interactions that a
single linear logistic equation cannot.

Eight small XGBoost configurations were tested chronologically. The selected
configuration was:

```text
n_estimators = 150
max_depth = 2
learning_rate = 0.03
min_child_weight = 5
subsample = 0.8
colsample_bytree = 0.8
```

The shallow depth and low learning rate intentionally keep the model
conservative.

### Fair model comparison

Both models used the same features and the same May-July mature test rows.
Neither model used test labels for tuning, calibration, or threshold selection.

| Metric | Logistic regression | XGBoost | Better |
|---|---:|---:|---|
| Moderate-or-High precision | 12.37% | 13.44% | XGBoost |
| Moderate-or-High recall | 70.95% | 76.67% | XGBoost |
| Moderate-or-High F1 | 21.06% | 22.87% | XGBoost |
| High precision | 20.15% | 30.80% | XGBoost |
| High recall | 50.95% | 34.76% | Logistic |
| High F1 | 28.88% | 32.66% | XGBoost |
| ROC-AUC | 0.727 | 0.757 | XGBoost |
| Average precision | 0.236 | 0.258 | XGBoost |
| Brier score | 0.0640 | 0.0632 | XGBoost |

### Why XGBoost was selected

The actionable review group is **Moderate or High**. At this boundary,
XGBoost improved recall, precision, and F1. Its High tier was narrower and
therefore had lower recall but substantially higher precision.

The selection rule required Moderate-or-High recall not to decrease, preferred
higher F1, required calibration to remain acceptable, and also compared
High-tier precision and ROC-AUC.

XGBoost satisfied that rule and was selected.

## Step 11: Retrain the selected model

After model selection, the mature test rows were no longer needed as a test
set. They became valid historical training data.

```text
Original training rows: 14,811
Mature May-July rows:     2,785
Final training rows:     17,596
```

Final training contained 1,811 B/C outcomes.

August's 836 immature examples were not used. “All available history” means
all sufficiently mature labelled history, not records whose final outcome is
not yet dependable.

The final probability calibration was learned from chronological out-of-fold
predictions:

1. Train on an older block.
2. Predict a later block that model has not seen.
3. Repeat across time.
4. Learn the probability correction from those out-of-fold predictions.
5. Fit the final XGBoost base model on all 17,596 mature rows.

Final deployment thresholds are:

```text
Low:      probability below 6.62%
Moderate: probability from 6.62% through 17.71%
High:     probability at least 17.71%
```

These differ from the earlier evaluation thresholds because the final model
was refitted and recalibrated on a larger historical dataset.

## Step 12: Build current restaurant features

The current scoring date was September 6, 2026.

For each restaurant, dbt selected its latest graded inspection and calculated:

- Latest known grade and score
- Earlier grade and score when available
- Historical violation and grade statistics
- Days from the latest grade to the scoring date
- Nearby matched complaints during the 90 days before the scoring date
- Cuisine and borough

The table contains 24,392 restaurants and passed 13 dbt tests.

The Phase 4 restaurant dimension contains 27,220 current restaurants. The
remaining 2,828 restaurants do not have sufficient graded history for this
model. They were not assigned invented or unreliable probabilities.

## Step 13: Produce current restaurant risk scores

The final model scored all 24,392 eligible restaurants.

| Risk category | Restaurants |
|---|---:|
| Low | 17,186 |
| Moderate | 4,837 |
| High | 2,369 |
| Total | 24,392 |

Mean current predicted risk: `7.73%`.

Every score includes:

```text
restaurant_id
restaurant_key
restaurant_name
address
scoring_date
risk_probability
risk_category
main_contributing_factors
model_version
scoring_timestamp
```

Example structure:

```json
{
  "restaurant_id": "50104757",
  "risk_probability": 0.184,
  "risk_category": "HIGH",
  "main_contributing_factors": [
    {"feature": "previous inspection violation count", "contribution": 0.42},
    {"feature": "days since last graded inspection", "contribution": 0.21}
  ],
  "model_version": "xgboost-final-20260906-v1",
  "scoring_timestamp": "2026-09-06T04:42:09.569830+00:00"
}
```

This is an illustrative layout. The actual factors and probabilities vary by
restaurant.

“Contributing” does not mean “caused.” These are model associations, not proof
that a feature caused a future grade.

## S3 output flow

```text
s3://safeeatsnyc-data-830460571487/ml/
|
|-- prepared/
|   `-- run_id=phase5-preparation-20260905-v1/
|       |-- X_train.npz
|       |-- X_test.npz
|       |-- y_train.npy
|       |-- y_test.npy
|       |-- train_rows.csv.gz
|       |-- test_rows.csv.gz
|       |-- preprocessor.joblib
|       |-- feature_names.json
|       `-- preparation_report.json
|
|-- models/
|   |-- logistic_regression/
|   `-- logistic_regression_calibrated/
|
|-- model_comparisons/
|   `-- run_id=logistic-vs-xgboost-20260906-v1/
|       |-- comparison_report.json
|       |-- xgboost_model_bundle.joblib
|       `-- xgboost_calibration_bins.csv
|
|-- final_models/
|   `-- run_id=xgboost-final-20260906-v1/
|       |-- model_bundle.joblib
|       `-- training_report.json
|
`-- current_scores/
    `-- run_id=current-risk-scores-20260906-v1/
        |-- current_restaurant_risk_scores.parquet
        |-- current_restaurant_risk_scores.csv.gz
        `-- scoring_report.json
```

The Parquet file is the preferred dashboard input. The compressed CSV is a
convenient inspection and recovery copy.

## Commands in order

### 1. Start in the repository and activate Python

```powershell
Set-Location E:\SafeEatsNYC
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
```

Verify AWS access when the login session may have expired:

```powershell
aws sts get-caller-identity `
  --profile safeeats-dev `
  --region us-east-1
```

If AWS says the session expired, refresh the existing AWS login before running
Docker jobs.

### 2. Build the modeling image

Run this after changing `ml/Dockerfile` or `ml/requirements.txt`:

```powershell
docker-compose --profile modeling build ml
```

Python-only source changes do not require rebuilding because the repository is
mounted into the container.

### 3. Build historical Phase 5 dbt models

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select ml_graded_inspections ml_inspection_targets ml_training_features `
  --profiles-dir .
```

Test them:

```powershell
docker-compose --profile warehouse run --rm dbt test `
  --select path:models/ml `
  --profiles-dir .
```

### 4. Prepare the chronological model data

The completed run ID already exists. Use a new run ID when rebuilding:

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.prepare_training_data `
  --run-id phase5-preparation-YYYYMMDD-v1 `
  --test-start-date 2026-05-01
```

Verify it:

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.verify_prepared_data `
  --run-id phase5-preparation-YYYYMMDD-v1
```

### 5. Train the logistic baseline

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.train_logistic_regression `
  --preparation-run-id phase5-preparation-YYYYMMDD-v1 `
  --model-run-id logistic-baseline-YYYYMMDD-v1 `
  --threshold-validation-start-date 2026-01-01
```

### 6. Tune and calibrate logistic regression

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.tune_calibrate_logistic `
  --preparation-run-id phase5-preparation-YYYYMMDD-v1 `
  --model-run-id logistic-calibrated-YYYYMMDD-v1 `
  --calibration-start-date 2026-01-01 `
  --threshold-start-date 2026-03-01 `
  --evaluation-end-date 2026-07-31
```

The dates must be reconsidered when the dataset is refreshed. Do not reuse
July 31 forever as the maturation cutoff.

### 7. Compare XGBoost with logistic regression

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.compare_xgboost `
  --preparation-run-id phase5-preparation-YYYYMMDD-v1 `
  --logistic-run-id logistic-calibrated-YYYYMMDD-v1 `
  --comparison-run-id logistic-vs-xgboost-YYYYMMDD-v1 `
  --calibration-start-date 2026-01-01 `
  --threshold-start-date 2026-03-01 `
  --evaluation-end-date 2026-07-31
```

### 8. Build the current scoring features

Use the actual scoring date:

```powershell
docker-compose --profile warehouse run --rm dbt run `
  --select ml_current_features `
  --vars "{ml_scoring_date: 'YYYY-MM-DD'}" `
  --profiles-dir .
```

Test them:

```powershell
docker-compose --profile warehouse run --rm dbt test `
  --select ml_current_features assert_ml_current_feature_history `
  --vars "{ml_scoring_date: 'YYYY-MM-DD'}" `
  --profiles-dir .
```

### 9. Retrain the winner and produce current scores

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.retrain_and_score `
  --preparation-run-id phase5-preparation-YYYYMMDD-v1 `
  --comparison-run-id logistic-vs-xgboost-YYYYMMDD-v1 `
  --final-model-run-id xgboost-final-YYYYMMDD-v1 `
  --score-run-id current-risk-scores-YYYYMMDD-v1 `
  --mature-through-date YYYY-MM-DD
```

Verify the final files:

```powershell
docker-compose --profile modeling run --rm ml `
  -m ml.verify_final_outputs `
  --final-model-run-id xgboost-final-YYYYMMDD-v1 `
  --score-run-id current-risk-scores-YYYYMMDD-v1
```

### 10. Run local Phase 5 Python tests

```powershell
docker-compose --profile modeling run --rm ml `
  -m pytest `
  tests/test_ml_preparation.py `
  tests/test_logistic_regression.py `
  tests/test_final_model.py `
  -q
```

Verified result: seven Python tests passed.

## Run-ID and replacement rule

Normal jobs reject an existing run ID. This protects model evidence from silent
overwrites.

For example, do not rerun:

```text
xgboost-final-20260906-v1
```

for a new dataset. Use a new version such as:

```text
xgboost-final-20260913-v1
```

The `--replace` option exists only to repair the exact same incomplete or
invalid artifact. It is not the normal refresh process.

## Verification completed

### dbt

- The historical ML models passed their Phase 5 tests.
- The current feature table produced 24,392 unique restaurant rows.
- All 13 current-feature dbt tests passed.
- Target alignment, same-day grade consistency, history arithmetic, and row
  reconciliation tests passed.

### Python

- Seven preparation, chronological-fold, threshold, calibration, and artifact
  tests passed.

### S3 read-back

The final verification confirmed:

- 24,392 Parquet rows
- 24,392 unique restaurant IDs
- Every probability between 0 and 1
- Only Low, Moderate, and High categories
- No nulls in required output fields
- At least two stored contributing factors per restaurant
- The score model version matches the reloadable final model bundle

## Known limitations

1. **Recent labels need time to mature.** A fixed calendar cutoff should not be
   hard-coded permanently. Each refresh must inspect recent N, Z, blank, A, B,
   and C distributions.
2. **Restaurants without graded history are not scored.** There are currently
   2,828 such restaurants.
3. **The probability predicts the next graded inspection outcome.** It does
   not directly predict food poisoning, closure, or a specific violation.
4. **Contributing factors are associations, not causes.** They help explain the
   model calculation but do not prove why a restaurant receives a grade.
5. **The deployed model is not automatically retrained by Airflow.** The Phase
   6 DAG refreshes Silver, Gold, and dbt feature tables, but the final model and
   current-risk score artifacts remain on their previous version until the
   controlled Phase 5 training workflow is run again.
6. **Model quality can drift.** Grade policy, inspection timing, complaint
   patterns, and restaurant populations can change. Metrics and calibration
   must be checked again after every retraining cycle.
7. **XGBoost is less transparent than logistic regression.** The logistic
   baseline and comparison report are retained for audit and explanation.

## Phase 5 completion checklist

- [x] Label represents the next graded inspection's B/C outcome.
- [x] Features contain only earlier information.
- [x] Time-based train/test split is used.
- [x] Logistic-regression baseline is trained.
- [x] Precision, recall, F1, ROC-AUC, and calibration are recorded.
- [x] Recent incomplete labels are identified and excluded from evaluation.
- [x] XGBoost is compared fairly with logistic regression.
- [x] Final model selection rule is documented.
- [x] Selected model is retrained on all mature history.
- [x] Final model artifact is stored in S3.
- [x] Current restaurant risk scores are stored in S3 Parquet.
- [x] Risk category, contributing factors, version, and timestamp are present.
- [x] Final model and scores pass read-back verification.

Phase 5 is complete for the current snapshot.
