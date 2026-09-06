with grades as (
    select * from (values 'A', 'B', 'C') as grade_values (grade)
),

areas as (
    select
        cast(borough_key as integer) as borough_key,
        borough_name,
        total_restaurants
    from {{ ref('dim_borough') }}

    union all

    select
        cast(0 as integer) as borough_key,
        'CITYWIDE' as borough_name,
        sum(total_restaurants) as total_restaurants
    from {{ ref('dim_borough') }}
),

borough_grade_counts as (
    select
        restaurants.borough_key,
        latest.grade,
        count(*) as restaurant_count
    from {{ ref('int_latest_graded_inspection') }} as latest
    join {{ ref('dim_restaurant') }} as restaurants
        on latest.restaurant_key = restaurants.restaurant_key
    where restaurants.borough_key is not null
    group by restaurants.borough_key, latest.grade
),

grade_counts as (
    select borough_key, grade, restaurant_count
    from borough_grade_counts

    union all

    select
        0 as borough_key,
        grade,
        sum(restaurant_count) as restaurant_count
    from borough_grade_counts
    group by grade
),

graded_totals as (
    select borough_key, sum(restaurant_count) as graded_restaurants
    from grade_counts
    group by borough_key
)

select
    to_hex(sha256(to_utf8(concat(cast(areas.borough_key as varchar), '||', grades.grade)))) as borough_grade_summary_key,
    case when areas.borough_key = 0 then 'CITYWIDE' else 'BOROUGH' end as area_level,
    areas.borough_key,
    areas.borough_name,
    grades.grade,
    coalesce(grade_counts.restaurant_count, 0) as restaurant_count,
    coalesce(graded_totals.graded_restaurants, 0) as graded_restaurants,
    areas.total_restaurants,
    100.0 * coalesce(grade_counts.restaurant_count, 0)
        / nullif(graded_totals.graded_restaurants, 0) as grade_percent_of_graded,
    100.0 * coalesce(grade_counts.restaurant_count, 0)
        / nullif(areas.total_restaurants, 0) as restaurants_per_100
from areas
cross join grades
left join grade_counts
    on areas.borough_key = grade_counts.borough_key
    and grades.grade = grade_counts.grade
left join graded_totals
    on areas.borough_key = graded_totals.borough_key
