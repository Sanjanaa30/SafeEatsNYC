# Full Restaurant Name Profile

This report uses distinct CAMIS/DBA pairs from the live NYC DOHMH 
Restaurant Inspection Results endpoint. Results reflect the source 
at execution time; the review queue never changes policy automatically.

- Distinct CAMIS/DBA pairs: 31,386
- Distinct CAMIS values: 31,386
- Distinct source DBA values: 24,636
- Distinct canonical names: 24,026
- Confirmed fast-food CAMIS values: 2,988
- Reviewed co-brand CAMIS values: 161
- Review-queue names: 3,035
- Names containing multiple known brands: 58
- Remaining possible alias names requiring review: 18

## Reviewed co-brands present

```
                                           dba                      brand_candidates  location_count
                       AUNTIE ANNE'S  CINNABON               AUNTIE ANNES | CINNABON               1
                        AUNTIE ANNE'S / CARVEL                 AUNTIE ANNES | CARVEL               2
                      AUNTIE ANNE'S / CINNABON               AUNTIE ANNES | CINNABON               1
             AUNTIE ANNE'S / CINNABON / CARVEL      AUNTIE ANNES | CINNABON | CARVEL               1
              AUNTIE ANNE'S PRETZEL / CINNABON               AUNTIE ANNES | CINNABON               1
           AUNTIE ANNE'S PRETZEL / JAMBA JUICE                  AUNTIE ANNES | JAMBA               1
                AUNTIE ANNE'S PRETZEL/CINNABON               AUNTIE ANNES | CINNABON               1
          AUNTIE ANNE'S PRETZELS / JAMBA JUICE                  AUNTIE ANNES | JAMBA               1
                AUNTIE ANNE'S PRETZELS, CARVEL                 AUNTIE ANNES | CARVEL               1
                        AUNTIE ANNE'S/CINNABON               AUNTIE ANNES | CINNABON               3
             Auntie Anne's / Cinnabon / Carvel      AUNTIE ANNES | CINNABON | CARVEL               1
               Auntie Anne’s/ Cinnabon/ Carvel      AUNTIE ANNES | CINNABON | CARVEL               1
                          BURGER KING, POPEYES                 BURGER KING | POPEYES               5
                             CARVEL & CINNABON                     CARVEL | CINNABON               1
                             CARVEL / CINNABON                     CARVEL | CINNABON               4
                               CARVEL CINNABON                     CARVEL | CINNABON               2
                   CARVEL-CINNABON-AUNTIEANNES      CARVEL | CINNABON | AUNTIE ANNES               1
                 CARVEL/AUNTIE ANNE'S/CINNABON      CARVEL | AUNTIE ANNES | CINNABON               1
                      CINNABON / AUNTIE ANNE'S               CINNABON | AUNTIE ANNES               1
             CINNABON / AUNTIE ANNE'S / CARVEL      CINNABON | AUNTIE ANNES | CARVEL               1
             CINNABON / AUNTIE ANNE'S PRETZELS               CINNABON | AUNTIE ANNES               1
                             CINNABON / CARVEL                     CINNABON | CARVEL               2
                         DUNKIN & JIMMY JOHN's                  DUNKIN | JIMMY JOHNS               1
DUNKIN (38CC)/ SHAKE SHACK (40CC) POST GATE 22                  DUNKIN | SHAKE SHACK               1
                       DUNKIN - BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
                       DUNKIN / BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               4
                         DUNKIN BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               3
      DUNKIN DONUT/JIMMY JOHN'S/BASKIN-ROBBINS DUNKIN | JIMMY JOHNS | BASKIN ROBBINS               1
                DUNKIN DONUTS / BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
                  DUNKIN DONUTS BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               2
                     DUNKIN' / 'BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS              11
                     DUNKIN' / 'BASKIN-ROBBINS               DUNKIN | BASKIN ROBBINS               1
                      DUNKIN' / BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS              30
                       DUNKIN' / BASKIN ROBINS               DUNKIN | BASKIN ROBBINS               1
                      DUNKIN' / BASKIN-ROBBINS               DUNKIN | BASKIN ROBBINS               2
                        DUNKIN' / JIMMY JOHN'S                  DUNKIN | JIMMY JOHNS               2
                             DUNKIN' / POPEYES                      DUNKIN | POPEYES               1
                                DUNKIN' BASKIN               DUNKIN | BASKIN ROBBINS               1
                        DUNKIN' BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
                         DUNKIN' BASKIN ROBINS               DUNKIN | BASKIN ROBBINS               2
                       DUNKIN' BASKIN-ROBBINS'               DUNKIN | BASKIN ROBBINS               1
                 DUNKIN' DONUTS/BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
         DUNKIN' DONUTS/JIMMY JOHNS/QNS MARKET                  DUNKIN | JIMMY JOHNS               1
                      DUNKIN', 'BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               7
                       DUNKIN', BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS              16
                      DUNKIN',' BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS              18
                 DUNKIN','PIZZA HUT',' NATHANS          DUNKIN | PIZZA HUT | NATHANS               1
           DUNKIN'-BASKIN-ROBBINS-JIMMY JOHN'S DUNKIN | BASKIN ROBBINS | JIMMY JOHNS               1
                        DUNKIN'/BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               2
                         DUNKIN, BASKIN ROBINS               DUNKIN | BASKIN ROBBINS               1
                         DUNKIN-BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
                         DUNKIN/BASKIN ROBBINS               DUNKIN | BASKIN ROBBINS               1
                           DUNKIN/JIMMY JOHN'S                  DUNKIN | JIMMY JOHNS               1
                            DUNKIN/JIMMY JOHNS                  DUNKIN | JIMMY JOHNS               1
           JAMBA JUICE/ AUNTIE ANNE'S PRETZELS                  JAMBA | AUNTIE ANNES               1
                               KFC / TACO BELL                       KFC | TACO BELL               2
                                KFC, TACO BELL                       KFC | TACO BELL               1
                                 KFC/TACO BELL                       KFC | TACO BELL               1
                               SUBWAY / CARVEL                       SUBWAY | CARVEL               1
                SUBWAY, KRISPY KRUNCHY CHICKEN       SUBWAY | KRISPY KRUNCHY CHICKEN               1
                           TACO BELL PIZZA HUT                 TACO BELL | PIZZA HUT               1
```

## Multiple-known-brand candidates

```
                                                              dba                 detected_known_brands  location_count
                                          AUNTIE ANNE'S  CINNABON               AUNTIE ANNES | CINNABON               1
                                           AUNTIE ANNE'S / CARVEL                 AUNTIE ANNES | CARVEL               2
                                         AUNTIE ANNE'S / CINNABON               AUNTIE ANNES | CINNABON               1
                                AUNTIE ANNE'S / CINNABON / CARVEL      AUNTIE ANNES | CARVEL | CINNABON               1
                                 AUNTIE ANNE'S PRETZEL / CINNABON               AUNTIE ANNES | CINNABON               1
                              AUNTIE ANNE'S PRETZEL / JAMBA JUICE                  AUNTIE ANNES | JAMBA               1
                                   AUNTIE ANNE'S PRETZEL/CINNABON               AUNTIE ANNES | CINNABON               1
                             AUNTIE ANNE'S PRETZELS / JAMBA JUICE                  AUNTIE ANNES | JAMBA               1
                                   AUNTIE ANNE'S PRETZELS, CARVEL                 AUNTIE ANNES | CARVEL               1
                                           AUNTIE ANNE'S/CINNABON               AUNTIE ANNES | CINNABON               3
                                Auntie Anne's / Cinnabon / Carvel      AUNTIE ANNES | CARVEL | CINNABON               1
                                  Auntie Anne’s/ Cinnabon/ Carvel      AUNTIE ANNES | CARVEL | CINNABON               1
                                             BURGER KING, POPEYES                 BURGER KING | POPEYES               5
                                                CARVEL & CINNABON                     CARVEL | CINNABON               1
                                                CARVEL / CINNABON                     CARVEL | CINNABON               4
                                                  CARVEL CINNABON                     CARVEL | CINNABON               2
                                      CARVEL-CINNABON-AUNTIEANNES                     CARVEL | CINNABON               1
                                    CARVEL/AUNTIE ANNE'S/CINNABON      AUNTIE ANNES | CARVEL | CINNABON               1
                                         CINNABON / AUNTIE ANNE'S               AUNTIE ANNES | CINNABON               1
                                CINNABON / AUNTIE ANNE'S / CARVEL      AUNTIE ANNES | CARVEL | CINNABON               1
                                CINNABON / AUNTIE ANNE'S PRETZELS               AUNTIE ANNES | CINNABON               1
                                                CINNABON / CARVEL                     CARVEL | CINNABON               2
                                            DUNKIN & JIMMY JOHN's                  DUNKIN | JIMMY JOHNS               1
                   DUNKIN (38CC)/ SHAKE SHACK (40CC) POST GATE 22                  DUNKIN | SHAKE SHACK               1
                                          DUNKIN - BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                          DUNKIN / BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               4
                                            DUNKIN BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               3
                         DUNKIN DONUT/JIMMY JOHN'S/BASKIN-ROBBINS BASKIN ROBBINS | DUNKIN | JIMMY JOHNS               1
                                   DUNKIN DONUTS / BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                     DUNKIN DONUTS BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               2
                                        DUNKIN' / 'BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN              11
                                        DUNKIN' / 'BASKIN-ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                         DUNKIN' / BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN              30
                                         DUNKIN' / BASKIN-ROBBINS               BASKIN ROBBINS | DUNKIN               2
                                           DUNKIN' / JIMMY JOHN'S                  DUNKIN | JIMMY JOHNS               2
                                                DUNKIN' / POPEYES                      DUNKIN | POPEYES               1
                                           DUNKIN' BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                          DUNKIN' BASKIN-ROBBINS'               BASKIN ROBBINS | DUNKIN               1
                                    DUNKIN' DONUTS/BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                            DUNKIN' DONUTS/JIMMY JOHNS/QNS MARKET                  DUNKIN | JIMMY JOHNS               1
                                         DUNKIN', 'BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               7
                                          DUNKIN', BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN              16
                                         DUNKIN',' BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN              18
                                    DUNKIN','PIZZA HUT',' NATHANS          DUNKIN | NATHANS | PIZZA HUT               1
                              DUNKIN'-BASKIN-ROBBINS-JIMMY JOHN'S BASKIN ROBBINS | DUNKIN | JIMMY JOHNS               1
                                           DUNKIN'/BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               2
                                            DUNKIN-BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                            DUNKIN/BASKIN ROBBINS               BASKIN ROBBINS | DUNKIN               1
                                              DUNKIN/JIMMY JOHN'S                  DUNKIN | JIMMY JOHNS               1
                                               DUNKIN/JIMMY JOHNS                  DUNKIN | JIMMY JOHNS               1
                              JAMBA JUICE/ AUNTIE ANNE'S PRETZELS                  AUNTIE ANNES | JAMBA               1
                                                  KFC / TACO BELL                       KFC | TACO BELL               2
                                                   KFC, TACO BELL                       KFC | TACO BELL               1
                                                    KFC/TACO BELL                       KFC | TACO BELL               1
                                                  SUBWAY / CARVEL                       CARVEL | SUBWAY               1
                                   SUBWAY, KRISPY KRUNCHY CHICKEN       KRISPY KRUNCHY CHICKEN | SUBWAY               1
                                              TACO BELL PIZZA HUT                 PIZZA HUT | TACO BELL               1
NATHAN'S FAMOUS (Kiosk in theme park by Bumper Cars/Wonder Wheel)                      NATHANS | WONDER               1
```

Full review queue: `docs\co_brand_review_queue.csv`
Alias review queue: `docs\brand_alias_review_queue.csv`
