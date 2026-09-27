# SafeEats NYC data dictionary

## Purpose

This dictionary explains the main datasets, their grains, identifiers, and
fields in plain language. It focuses on fields used by the warehouse, model,
API, and dashboard.

The executable schemas remain the final technical authority:

- **spark/schemas.py** for Bronze and Silver types
- **dbt/models/**/*.sql** for warehouse columns
- **dbt/models/**/*.yml** for dbt descriptions and tests
- **api/schemas/** for public API response validation

## Shared terms

| Term | Meaning |
|---|---|
| CAMIS | NYC Department of Health restaurant identifier |
| Restaurant key | SHA-256 warehouse key created from CAMIS |
| Inspection ID | Warehouse identifier for one restaurant, inspection date, and inspection type |
| Grade | Official recorded A, B, or C grade where available |
| Score | Inspection points; a higher score generally represents more problems |
| Critical finding | A violation marked Critical by the source |
| Complaint match | The nearest eligible restaurant within the configured 100-meter threshold |
| Current restaurant | Latest deterministic restaurant record for a CAMIS |
| Chain or group | A reviewed or high-confidence family of multiple restaurant locations |
| Prediction anchor | The last known graded inspection used to predict the next one |

## Source data

### NYC restaurant inspections

Dataset ID: **43nn-pn8j**

Source grain: one row per restaurant inspection and violation combination. An
inspection with several violations therefore appears in several source rows.

Important source fields:

| Field | Meaning |
|---|---|
| camis | Stable restaurant ID used by DOHMH |
| dba | Restaurant name published by DOHMH |
| boro | Borough |
| building, street, zipcode | Address parts |
| cuisine_description | DOHMH cuisine category |
| inspection_date | Date of the inspection |
| inspection_type | Type and cycle of inspection |
| action | Resulting inspection action |
| violation_code | DOHMH violation code |
| violation_description | Full DOHMH wording |
| critical_flag | Critical or non-critical source classification |
| score | Inspection points |
| grade | Published grade when present |
| grade_date | Date associated with the grade |
| record_date | Source record timestamp |
| latitude, longitude | Restaurant coordinates |

Identifiers such as CAMIS and ZIP remain strings so leading zeroes are not
lost.

### NYC 311 complaints

Dataset ID: **erm2-nwe9**

Source grain: one row per service request.

Only Food Establishment, Food Poisoning, and Rodent complaint types are loaded.

Important source fields:

| Field | Meaning |
|---|---|
| unique_key | Unique 311 service-request ID |
| created_date | Time the request was created |
| closed_date | Time the request was closed, when available |
| complaint_type | High-level complaint category |
| descriptor | More specific complaint description |
| location_type | Type of reported location |
| incident_zip | Reported ZIP code |
| incident_address | Reported address |
| borough | Reported borough |
| status | Current request status |
| latitude, longitude | Complaint coordinates |

## Bronze layer

Bronze retains source values without converting or renaming them.

Each run folder contains:

| File | Meaning |
|---|---|
| request.json | Source, date window, filters, run ID, and request settings |
| page_offset=NNN.json | One unchanged paginated API response |

Important partition values:

| Value | Meaning |
|---|---|
| ingest_date | Date the project downloaded the data |
| run_id | One logical pipeline execution |
| page offset | Starting row position of an API page |

## Silver inspections

Grain: one deduplicated inspection-and-violation record.

| Field | Meaning |
|---|---|
| inspection_violation_id | Unique key for the Silver row |
| camis | DOHMH restaurant ID |
| restaurant_name_original | Original DOHMH restaurant name |
| restaurant_name_normalized | Separate cleaned name used for matching |
| fast_food_brand_names | Reviewed matched brand names |
| is_reviewed_co_brand | Whether the location has reviewed multiple-brand associations |
| is_fast_food | Whether a reviewed brand matches the quick-service registry |
| borough | Standardized borough |
| address_display | Combined display address |
| zipcode | Five-digit ZIP where available |
| cuisine_description | DOHMH cuisine category |
| inspection_date | Typed inspection timestamp |
| violation_code | DOHMH violation code |
| violation_description | Full source wording |
| critical_flag | Source criticality label |
| score | Integer inspection score |
| grade | Source grade |
| inspection_type | Inspection type and cycle |
| action | Inspection action |
| record_date | Typed source record timestamp |
| latitude, longitude | Validated numeric coordinates |
| coordinate_status | Why coordinates are usable or unusable |
| inspection_year, inspection_month | S3 partition fields |

The same inspection may have several rows because violations remain separate.

## Silver complaints and matches

Grain: one deduplicated 311 service request.

| Field | Meaning |
|---|---|
| unique_key | 311 complaint ID |
| created_date, closed_date | Typed complaint timestamps |
| complaint_type | Standardized relevant complaint category |
| descriptor | More specific complaint wording |
| location_type | Reported location category |
| incident_zip, incident_address | Reported location text |
| borough | Standardized borough |
| status | Complaint status |
| latitude, longitude | Complaint coordinates |
| restaurant_camis | Matched restaurant ID, when matched |
| matched_restaurant_name | Name of the nearest matched restaurant |
| matched_restaurant_address | Address of the matched restaurant |
| restaurant_latitude, restaurant_longitude | Coordinates used for the restaurant match |
| nearest_candidate_distance_meters | Distance to the nearest candidate |
| match_distance_meters | Accepted match distance |
| restaurant_match_status | MATCHED, NO_RESTAURANT_WITHIN_THRESHOLD, or NO_VALID_COORDINATES |
| match_threshold_meters | Maximum accepted distance, normally 100 meters |
| complaint_year, complaint_month | S3 partition fields |

An unmatched complaint remains in Silver with a null restaurant ID.

## Gold staging and intermediate models

| Model | Grain | Purpose |
|---|---|---|
| stg_inspections | One Silver inspection-and-violation row | Renames and standardizes inspection fields |
| stg_complaints | One Silver complaint row | Renames complaint and match fields |
| int_inspection_events | One inspection event | Prevents violation rows from multiplying inspection measures |
| int_latest_graded_inspection | One latest A/B/C inspection per restaurant | Supports current grade views |
| stg_restaurant_current | One current row per CAMIS | Selects current restaurant attributes |
| stg_chain_flags | One current row per CAMIS | Adds restaurant-group and brand flags |

## Gold dimensions

### dim_restaurant

Grain: one current Type 1 row per CAMIS.

| Field | Meaning |
|---|---|
| restaurant_key | Hashed warehouse key |
| camis | DOHMH restaurant ID |
| restaurant_name | Current display name |
| restaurant_name_normalized | Matching name |
| address, zipcode | Current address |
| nta_code, nta_name | Approximate neighborhood assignment from ZIP |
| borough_key | Link to dim_borough |
| cuisine | Current cuisine |
| latitude, longitude | Current valid coordinates where available |
| coordinate_status | Coordinate quality status |
| normalized_name_location_count | Number of locations sharing the normalized name |
| is_chain | Whether group rules identify a multi-location family |
| is_confirmed_fast_food | Whether a reviewed brand is in quick-service scope |
| is_reviewed_co_brand | Whether multiple brands were manually reviewed |
| chain_key | Link to dim_chain when grouped |
| chain_family_name | Display name for the group |
| chain_match_method | Rule that created the group match |
| chain_match_confidence | HIGH or NONE in the current policy |
| is_current | Current-record flag |

Type 1 means that the table keeps the current restaurant attributes rather than
a full effective-dated history of address or cuisine changes.

### Other dimensions

| Table | Grain | Important fields |
|---|---|---|
| dim_chain | One detected group | chain_key, chain_name, location_count, borough_count, is_confirmed_fast_food |
| dim_borough | One NYC borough | borough_key, borough_name, total_restaurants |
| dim_date | One calendar day | date_key, calendar_date, year, quarter, month, week, weekday, is_weekend |
| dim_violation | One non-null violation code | violation_key, violation_code, violation_description, is_critical |
| dim_complaint_type | One complaint category | complaint_type_key, complaint_type |

## Gold facts

### fact_inspection

Grain: one deduplicated inspection-and-violation record.

| Field | Meaning |
|---|---|
| inspection_event_key | Unique source-row key |
| inspection_id | Shared identifier for all violation rows in one inspection |
| restaurant_key | Link to dim_restaurant |
| date_key | Link to dim_date |
| violation_key | Link to dim_violation; null when no violation exists |
| borough_key | Link to dim_borough |
| score | Inspection score |
| grade | Recorded grade |
| inspection_type | Inspection type |
| inspection_action | Recorded action |
| is_critical | True when the violation is critical |

Use distinct inspection_id or int_inspection_events for inspection counts.

### fact_311_complaint

Grain: one unique 311 complaint.

| Field | Meaning |
|---|---|
| complaint_id | 311 unique key |
| restaurant_key | Matched restaurant; null when unmatched |
| date_key | Link to dim_date |
| complaint_type_key | Link to dim_complaint_type |
| borough_key | Link to dim_borough |
| created_date, closed_date | Complaint timestamps |
| status | Request status |
| descriptor | Detailed complaint type |
| location_type | Reported location type |
| incident_zip, incident_address | Reported location |
| latitude, longitude | Complaint coordinates |
| restaurant_match_status | Match outcome |
| match_distance_meters | Accepted match distance |
| match_threshold_meters | Configured maximum match distance |

## Dashboard marts

| Mart | Grain | Main use |
|---|---|---|
| mart_borough_grade_summary | One borough or citywide area and grade | Current A/B/C distribution |
| mart_cuisine_borough_heatmap | One cuisine and borough | Grade shares and cuisine attention |
| mart_violation_by_borough | One violation and borough | Finding frequency and affected restaurants |
| mart_weekly_311_vs_inspection | One week and borough or citywide area | Complaint and critical-inspection trends |
| mart_restaurant_grade_history | One graded restaurant inspection | Finder history and improvement indicators |
| mart_chain_summary | One detected restaurant group | Location, borough, grade, and risk summaries |

Important calculated measures:

| Measure | Definition |
|---|---|
| grade_percent_of_graded | Restaurants with a selected grade divided by restaurants with A/B/C grades |
| violations_per_100_restaurants | Violation rows divided by current restaurants, multiplied by 100 |
| complaints_per_1000_restaurants | Weekly complaints divided by current restaurants, multiplied by 1,000 in the API |
| inspections_with_critical_per_100 | Inspections containing at least one critical finding divided by inspections, multiplied by 100 |
| correlation | Pearson relationship between paired weekly complaint and inspection rates |

One inspection can contain more than one finding, so a finding rate is not
always the same as the percentage of inspections affected.

## Machine-learning tables

| Model | Grain | Purpose |
|---|---|---|
| ml_graded_inspections | One graded restaurant date | Consolidates A/B/C inspection history |
| ml_inspection_targets | One earlier inspection paired with the next graded inspection | Creates the future A versus B/C label |
| ml_training_features | One historical prediction anchor | Supplies past-only training features and known outcome |
| ml_current_features | One eligible current restaurant | Supplies the latest state for scoring |

Important model fields:

| Field | Meaning |
|---|---|
| prediction_anchor_key | Inspection state known at prediction time |
| prediction_anchor_date | Date of that known inspection |
| target_inspection_key | Strictly later inspection used as the training outcome |
| target_inspection_date | Date of the outcome inspection |
| target_grade | Actual later grade |
| target_is_bc | 1 when the later grade is B/C, otherwise 0 |
| previous_grade, previous_score | Most recent known inspection result |
| earlier_grade, earlier_score | Inspection before the most recent known result |
| recent_score_change | Change between the last two known scores |
| recent_3_inspection_avg_score | Average score over up to three known inspections |
| historical_* | Counts and rates from known earlier history |
| days_since_last_graded_inspection | Time since the known inspection |
| prior_90d_*_complaint_count | Nearby complaint counts from the allowed earlier window |
| scoring_date | Date represented by a current feature row |

## Approved risk-score output

Grain: one eligible current restaurant.

Core fields include:

| Field | Meaning |
|---|---|
| restaurant_key | Warehouse restaurant identifier |
| restaurant_id | DOHMH CAMIS value |
| risk_probability | Calibrated estimated probability from 0 to 1 |
| risk_category | LOW, MODERATE, or HIGH |
| model_version | Exact trained model version |
| scoring_timestamp | Score creation time |
| main_contributing_factors | Stored restaurant-level factor contributions |

Not every restaurant receives a score. Restaurants without enough graded
history remain available in Finder but do not appear in the scored population.

## Reference files

See the [static reference-data guide](README.md) for borough boundaries,
ZIP-to-NTA assignment, brand aliases, classification overrides, and co-brand
associations.

## Related documents

- [Architecture](architecture.md)
- [Data quality and limitations](data_quality_and_limitations.md)
- [Warehouse guide](phase4_warehouse.md)
- [Predictive model](phase5_predictive_model.md)
