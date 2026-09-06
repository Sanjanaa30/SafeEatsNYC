with graded_history as (
    select
        inspections.*,
        dates.calendar_date as inspection_date,
        lag(inspections.grade) over (
            partition by inspections.restaurant_key
            order by inspections.date_key, inspections.inspection_id
        ) as previous_grade,
        row_number() over (
            partition by inspections.restaurant_key
            order by inspections.date_key desc, inspections.inspection_id desc
        ) as inspection_recency_rank
    from {{ ref('int_inspection_events') }} as inspections
    join {{ ref('dim_date') }} as dates on inspections.date_key = dates.date_key
    where inspections.grade in ('A', 'B', 'C')
),

restaurant_grade_stats as (
    select
        restaurant_key,
        count(*) as graded_inspection_count,
        count(distinct grade) as distinct_grade_count,
        min(inspection_date) as first_graded_inspection_date,
        max(inspection_date) as latest_graded_inspection_date,
        min(case when grade = 'A' then 1 else 0 end) = 1 as is_consistently_grade_a
    from graded_history
    group by restaurant_key
)

select
    history.inspection_id as restaurant_grade_history_key,
    history.inspection_id,
    history.restaurant_key,
    restaurants.camis,
    restaurants.restaurant_name,
    restaurants.restaurant_name_normalized,
    restaurants.address,
    restaurants.zipcode,
    restaurants.nta_name,
    restaurants.borough_key,
    boroughs.borough_name,
    restaurants.cuisine,
    restaurants.latitude,
    restaurants.longitude,
    restaurants.is_chain,
    restaurants.is_confirmed_fast_food,
    restaurants.chain_key,
    history.date_key,
    history.inspection_date,
    history.grade,
    history.previous_grade,
    history.score,
    history.violation_count,
    history.critical_violation_count,
    history.has_critical_violation,
    history.inspection_recency_rank,
    history.inspection_recency_rank = 1 as is_latest_graded_inspection,
    history.grade = 'A' and history.previous_grade in ('B', 'C') as improved_to_a,
    date_diff('day', history.inspection_date, current_date) as days_since_inspection,
    stats.graded_inspection_count,
    stats.distinct_grade_count = 1 as is_grade_consistent,
    stats.is_consistently_grade_a,
    stats.first_graded_inspection_date,
    stats.latest_graded_inspection_date
from graded_history as history
join restaurant_grade_stats as stats
    on history.restaurant_key = stats.restaurant_key
join {{ ref('dim_restaurant') }} as restaurants
    on history.restaurant_key = restaurants.restaurant_key
left join {{ ref('dim_borough') }} as boroughs
    on restaurants.borough_key = boroughs.borough_key
