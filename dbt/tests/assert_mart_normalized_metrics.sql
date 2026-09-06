select 'borough_grade' as mart_name, borough_grade_summary_key as row_key
from {{ ref('mart_borough_grade_summary') }}
where abs(
    restaurants_per_100
    - (100.0 * restaurant_count / nullif(total_restaurants, 0))
) > 0.000001

union all

select 'cuisine_heatmap', cuisine_borough_key
from {{ ref('mart_cuisine_borough_heatmap') }}
where abs(
    grade_a_per_100_restaurants
    - (100.0 * grade_a_restaurants / nullif(total_restaurants, 0))
) > 0.000001

union all

select 'violation_borough', violation_borough_key
from {{ ref('mart_violation_by_borough') }}
where abs(
    violations_per_100_restaurants
    - (100.0 * violation_count / nullif(total_restaurants, 0))
) > 0.000001

union all

select 'weekly', weekly_area_key
from {{ ref('mart_weekly_311_vs_inspection') }}
where abs(
    complaints_per_100_restaurants
    - (100.0 * complaint_count / nullif(total_restaurants, 0))
) > 0.000001
or abs(
    critical_violations_per_100_restaurants
    - (100.0 * critical_violation_count / nullif(total_restaurants, 0))
) > 0.000001
