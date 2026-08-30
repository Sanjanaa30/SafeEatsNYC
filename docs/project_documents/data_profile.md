# Phase 1 Data Profile

This report profiles the small NYC Open Data samples used for schema and data-quality exploration.

The samples are not the full production datasets.

## Sample summary

- Inspection rows: 1,000
- Inspection fields observed: 27
- Unique restaurants (`camis`): 274
- 311 rows: 1,000
- 311 fields observed: 35

## Inspection fields observed

action, bbl, bin, boro, building, camis, census_tract, community_board, council_district, critical_flag, cuisine_description, dba, grade, grade_date, inspection_date, inspection_type, latitude, location, longitude, nta, phone, record_date, score, street, violation_code, violation_description, zipcode

## 311 fields observed

address_type, agency, agency_name, bbl, borough, city, closed_date, community_board, complaint_type, council_district, created_date, cross_street_1, cross_street_2, descriptor, descriptor_2, incident_address, incident_zip, intersection_street_1, intersection_street_2, landmark, latitude, location, location_type, longitude, open_data_channel_type, park_borough, park_facility_name, police_precinct, resolution_action_updated_date, resolution_description, status, street_name, unique_key, x_coordinate_state_plane, y_coordinate_state_plane

## Inspection key-field missingness

```
                field  missing_count  missing_percent
                camis              0              0.0
                  dba              0              0.0
                 boro              0              0.0
             building              3              0.3
               street              0              0.0
              zipcode              7              0.7
             latitude              3              0.3
            longitude              3              0.3
  cuisine_description              0              0.0
      inspection_date              0              0.0
               action              0              0.0
       violation_code              8              0.8
violation_description              8              0.8
        critical_flag              0              0.0
                score             51              5.1
                grade            371             37.1
           grade_date            539             53.9
```

## 311 key-field missingness

```
         field  missing_count  missing_percent
    unique_key              0              0.0
  created_date              0              0.0
complaint_type              0              0.0
    descriptor              0              0.0
  incident_zip              4              0.4
      latitude              5              0.5
     longitude              5              0.5
       borough              0              0.0
        status              0              0.0
```

## Inspection borough values

```
         boro  row_count
    Manhattan        365
       Queens        279
     Brooklyn        209
        Bronx        130
Staten Island         17
```

## Inspection grade values

```
    grade  row_count
<missing>        371
        A        307
        N        168
        Z        154
```

## Inspection critical-flag values

```
 critical_flag  row_count
      Critical        521
  Not Critical        465
Not Applicable         14
```

## 311 complaint types

```
    complaint_type  row_count
            Rodent        649
Food Establishment        293
    Food Poisoning         58
```

## 311 borough values

```
      borough  row_count
     BROOKLYN        301
    MANHATTAN        280
       QUEENS        243
        BRONX        121
STATEN ISLAND         51
  Unspecified          4
```

## 311 status values

```
     status  row_count
In Progress        884
     Closed        116
```

## Duplicate and grain checks

- Exact duplicate inspection rows: 0
- Estimated inspection events: 307
- Inspection events with multiple violation rows: 246
- Largest number of rows for one inspection event: 12
- CAMIS values with multiple DBA names in the sample: 0
- Exact duplicate 311 rows: 0
- Duplicate 311 `unique_key` values: 0

## Restaurant-name harmonization

This profile applies the same syntax normalization and reviewed alias rules used to build the fast-food brand reference. Co-brands are expanded only through the reviewed association file; punctuation and words such as `AND` are not splitting rules.

- Unique source DBA values: 261
- Unique values after syntax normalization: 258
- Unique values after reviewed aliases: 256
- CAMIS values changed by a reviewed alias: 3
- CAMIS values with a reviewed co-brand association: 3
- CAMIS values exactly matching at least one fast-food brand: 32
- Distinct names containing a possible separator: 27

### Source names merged by normalization or aliases

```
name_normalized                source_dba_values
        DOMINOS  DOMINO'S | DOMINO'S PIZZA #3685
         DUNKIN DUNKIN | DUNKIN DONUTS | DUNKIN'
 LOS TACOS NO 1 LOS TACOS NO. 1 | LOS TACOS NO.1
         WENDYS                 WENDY'S | WENDYS
```

### Reviewed co-brand associations

```
                 location_name_normalized                      brands_preserved  sample_camis
                    DUNKIN BASKIN ROBBINS               DUNKIN + BASKIN ROBBINS             1
                     DUNKIN BASKIN ROBINS               DUNKIN + BASKIN ROBBINS             0
                            DUNKIN BASKIN               DUNKIN + BASKIN ROBBINS             0
                    AUNTIE ANNES CINNABON               AUNTIE ANNES + CINNABON             2
             AUNTIE ANNES CINNABON CARVEL      AUNTIE ANNES + CINNABON + CARVEL             0
            AUNTIE ANNES PRETZEL CINNABON               AUNTIE ANNES + CINNABON             0
         AUNTIE ANNES PRETZEL JAMBA JUICE                  AUNTIE ANNES + JAMBA             0
        AUNTIE ANNES PRETZELS JAMBA JUICE                  AUNTIE ANNES + JAMBA             0
                      AUNTIE ANNES CARVEL                 AUNTIE ANNES + CARVEL             0
             AUNTIE ANNES PRETZELS CARVEL                 AUNTIE ANNES + CARVEL             0
                      BURGER KING POPEYES                 BURGER KING + POPEYES             0
             CARVEL AUNTIE ANNES CINNABON      CARVEL + AUNTIE ANNES + CINNABON             0
                          CARVEL CINNABON                     CARVEL + CINNABON             0
                      CARVEL AND CINNABON                     CARVEL + CINNABON             0
              CARVEL CINNABON AUNTIEANNES      CARVEL + CINNABON + AUNTIE ANNES             0
                    CINNABON AUNTIE ANNES               CINNABON + AUNTIE ANNES             0
             CINNABON AUNTIE ANNES CARVEL      CINNABON + AUNTIE ANNES + CARVEL             0
           CINNABON AUNTIE ANNES PRETZELS               CINNABON + AUNTIE ANNES             0
                          CINNABON CARVEL                     CINNABON + CARVEL             0
                   DUNKIN AND JIMMY JOHNS                  DUNKIN + JIMMY JOHNS             0
DUNKIN 38CC SHAKE SHACK 40CC POST GATE 22                  DUNKIN + SHAKE SHACK             0
  DUNKIN DONUT JIMMY JOHNS BASKIN ROBBINS DUNKIN + JIMMY JOHNS + BASKIN ROBBINS             0
             DUNKIN DONUTS BASKIN ROBBINS               DUNKIN + BASKIN ROBBINS             0
                       DUNKIN JIMMY JOHNS                  DUNKIN + JIMMY JOHNS             0
                           DUNKIN POPEYES                      DUNKIN + POPEYES             0
     DUNKIN DONUTS JIMMY JOHNS QNS MARKET                  DUNKIN + JIMMY JOHNS             0
                 DUNKIN PIZZA HUT NATHANS          DUNKIN + PIZZA HUT + NATHANS             0
        DUNKIN BASKIN ROBBINS JIMMY JOHNS DUNKIN + BASKIN ROBBINS + JIMMY JOHNS             0
        JAMBA JUICE AUNTIE ANNES PRETZELS                  JAMBA + AUNTIE ANNES             0
                            KFC TACO BELL                       KFC + TACO BELL             0
            SUBWAY KRISPY KRUNCHY CHICKEN       SUBWAY + KRISPY KRUNCHY CHICKEN             0
                            SUBWAY CARVEL                       SUBWAY + CARVEL             0
                      TACO BELL PIZZA HUT                 TACO BELL + PIZZA HUT             0
```

The separator count is a review queue, not a co-brand count. For example, `FRESH AND CO` and `JOE & THE JUICE` are single names.

### Separator review queue

```
                                dba               name_syntax_normalized  sample_camis                  policy
          AREA LATINA BAR AND GRILL            AREA LATINA BAR AND GRILL             1 REVIEW ONLY - NOT SPLIT
             AUGIES DELI & PIZZERIA             AUGIES DELI AND PIZZERIA             1 REVIEW ONLY - NOT SPLIT
             AUNTIE ANNE'S/CINNABON                AUNTIE ANNES CINNABON             2       REVIEWED CO-BRAND
                   BAGELS AND CREAM                     BAGELS AND CREAM             1 REVIEW ONLY - NOT SPLIT
                      BIRD & BRANCH                      BIRD AND BRANCH             1 REVIEW ONLY - NOT SPLIT
             COCO FRESH TEA & JUICE             COCO FRESH TEA AND JUICE             1 REVIEW ONLY - NOT SPLIT
         DELICIAS PIZZA AND CHICKEN           DELICIAS PIZZA AND CHICKEN             1 REVIEW ONLY - NOT SPLIT
           DUNKIN',' BASKIN ROBBINS                DUNKIN BASKIN ROBBINS             1       REVIEWED CO-BRAND
   ELCIELO NEW YORK / THE POOL CLUB       ELCIELO NEW YORK THE POOL CLUB             1 REVIEW ONLY - NOT SPLIT
     GROWL GROWL HOT POT & COCKTAIL     GROWL GROWL HOT POT AND COCKTAIL             1 REVIEW ONLY - NOT SPLIT
                    JOE & THE JUICE                    JOE AND THE JUICE             1 REVIEW ONLY - NOT SPLIT
                 JUS FISHY & BEYOND                 JUS FISHY AND BEYOND             1 REVIEW ONLY - NOT SPLIT
          LA QUINTA INNS AND SUITES            LA QUINTA INNS AND SUITES             1 REVIEW ONLY - NOT SPLIT
     MASALLAH SWEETS AND RESTAURANT       MASALLAH SWEETS AND RESTAURANT             1 REVIEW ONLY - NOT SPLIT
                   MERGUEZ & FRITES                   MERGUEZ AND FRITES             1 REVIEW ONLY - NOT SPLIT
             MONTE GRAB & GO MARKET             MONTE GRAB AND GO MARKET             1 REVIEW ONLY - NOT SPLIT
 NEW YORK CITY BAGEL & COFFEE HOUSE NEW YORK CITY BAGEL AND COFFEE HOUSE             1 REVIEW ONLY - NOT SPLIT
 NU3S - CAR WASH / CAFE / AUTO CARE         NU3S CAR WASH CAFE AUTO CARE             1 REVIEW ONLY - NOT SPLIT
                  P & Y COFFEE SHOP                  P AND Y COFFEE SHOP             1 REVIEW ONLY - NOT SPLIT
               PETE'S DINER & GRILL                PETES DINER AND GRILL             1 REVIEW ONLY - NOT SPLIT
                QIU SUSHI & TEA BAR                QIU SUSHI AND TEA BAR             1 REVIEW ONLY - NOT SPLIT
                  ROPES & GRAY CAFE                  ROPES AND GRAY CAFE             1 REVIEW ONLY - NOT SPLIT
SALUMERIA BEILLESE, BIRICCHINO REST   SALUMERIA BEILLESE BIRICCHINO REST             1 REVIEW ONLY - NOT SPLIT
                      SLURP & SWIRL                      SLURP AND SWIRL             1 REVIEW ONLY - NOT SPLIT
      TEPANGOS PIZZA & MEXICAN FOOD      TEPANGOS PIZZA AND MEXICAN FOOD             1 REVIEW ONLY - NOT SPLIT
    THE PENNY FARTHING & Linen Hall    THE PENNY FARTHING AND LINEN HALL             1 REVIEW ONLY - NOT SPLIT
                      TOAST & ROAST                      TOAST AND ROAST             1 REVIEW ONLY - NOT SPLIT
```

## Date checks

- Inspection minimum date: 2026-08-21T00:00:00
- Inspection maximum date: 2026-08-25T00:00:00
- Unparseable inspection dates: 0
- `1900-01-01` inspection sentinel rows: 0
- 311 minimum created date: 2026-08-21T17:44:28
- 311 maximum created date: 2026-08-28T02:00:17
- Unparseable 311 created dates: 0

## Coordinate checks

### Inspections

- Missing coordinate pairs: 3
- Zero coordinate pairs: 7
- Outside approximate NYC bounds: 0
- Usable coordinate pairs: 990

### 311 complaints

- Missing coordinate pairs: 5
- Zero coordinate pairs: 0
- Outside approximate NYC bounds: 0
- Usable coordinate pairs: 995

## Inspection score checks

- Minimum parseable score: 0.0
- Maximum parseable score: 87.0
- Non-numeric populated scores: 0

## Complaint-filter validation

- Complaint types returned: ['Food Establishment', 'Food Poisoning', 'Rodent']
- Unexpected complaint types: []

## Dashboard-field mapping

- Page 1 uses restaurant, borough, cuisine, grade, score, critical flag, action, and violation fields.
- Page 2 uses inspection and complaint dates, boroughs, complaint types, critical violations, and coordinates.
- Page 3 uses CAMIS, restaurant name, address, ZIP, cuisine, grade, inspection date, score, and violations.
- Page 4 will use historical inspection fields to build the B/C-risk features.

## Initial data-quality decisions

1. Preserve the original Bronze JSON without modification.
2. Parse dates and numeric values explicitly in Silver.
3. Treat `1900-01-01` as a not-yet-inspected sentinel, not a real inspection date.
4. Preserve legitimate multiple violation rows belonging to one inspection event.
5. Deduplicate exact records and duplicate 311 keys using documented rules.
6. Standardize borough capitalization between sources.
7. Treat missing, zero, or out-of-range coordinates as unusable for geospatial matching.
8. Preserve source grades such as N, Z, and P in Silver; filter or map them only when building graded Gold metrics.
9. Do not calculate dashboard KPIs from this recent 1,000-row sample.
10. Use the later historical ingestion for three-year grade history, correlation, and ML training.
