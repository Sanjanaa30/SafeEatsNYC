{% set scoring_date = var('ml_scoring_date', '2026-09-06') %}

with history as (
    select
        inspections.*,
        lag(grade) over (
            partition by restaurant_key order by inspection_date
        ) as earlier_grade,
        lag(score) over (
            partition by restaurant_key order by inspection_date
        ) as earlier_score,
        date_diff(
            'day',
            lag(inspection_date) over (
                partition by restaurant_key order by inspection_date
            ),
            inspection_date
        ) as days_between_last_two_graded_inspections,
        avg(score) over (
            partition by restaurant_key order by inspection_date
            rows between 2 preceding and current row
        ) as recent_3_inspection_avg_score,
        sum(critical_violation_count) over (
            partition by restaurant_key order by inspection_date
            rows between 2 preceding and current row
        ) as recent_3_critical_violation_count,
        sum(case when has_critical_violation then 1 else 0 end) over (
            partition by restaurant_key order by inspection_date
            rows between 2 preceding and current row
        ) as recent_3_inspections_with_critical,
        row_number() over (
            partition by restaurant_key order by inspection_date
        ) as known_graded_inspection_count,
        row_number() over (
            partition by restaurant_key order by inspection_date desc
        ) as inspection_recency_rank,
        sum(violation_count) over (
            partition by restaurant_key order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_violation_count,
        sum(critical_violation_count) over (
            partition by restaurant_key order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_critical_violation_count,
        sum(case when grade = 'A' then 1 else 0 end) over (
            partition by restaurant_key order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_a_count,
        sum(case when grade = 'B' then 1 else 0 end) over (
            partition by restaurant_key order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_b_count,
        sum(case when grade = 'C' then 1 else 0 end) over (
            partition by restaurant_key order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_c_count
    from {{ ref('ml_graded_inspections') }} as inspections
),

latest_history as (
    select *
    from history
    where inspection_recency_rank = 1
),

recent_complaints as (
    select
        latest.graded_inspection_key,
        count(complaints.complaint_id) as prior_90d_nearby_complaint_count,
        sum(case when complaints.complaint_type = 'RODENT' then 1 else 0 end) as prior_90d_rodent_complaint_count,
        sum(case when complaints.complaint_type = 'FOOD POISONING' then 1 else 0 end) as prior_90d_food_poisoning_complaint_count,
        sum(case when complaints.complaint_type = 'FOOD ESTABLISHMENT' then 1 else 0 end) as prior_90d_food_establishment_complaint_count
    from latest_history as latest
    join {{ ref('dim_restaurant') }} as restaurants
        on latest.restaurant_key = restaurants.restaurant_key
    left join {{ ref('stg_complaints') }} as complaints
        on complaints.restaurant_camis = restaurants.camis
        and complaints.restaurant_match_status = 'MATCHED'
        and complaints.created_date >= cast(
            date_add('day', -90, cast('{{ scoring_date }}' as date)) as timestamp
        )
        and complaints.created_date < cast('{{ scoring_date }}' as timestamp)
        and abs(complaints.restaurant_latitude - latest.latitude) <= 0.000001
        and abs(complaints.restaurant_longitude - latest.longitude) <= 0.000001
    group by latest.graded_inspection_key
)

select
    latest.graded_inspection_key as prediction_anchor_key,
    latest.restaurant_key,
    restaurants.camis,
    restaurants.restaurant_name,
    restaurants.address,
    cast('{{ scoring_date }}' as date) as scoring_date,
    latest.inspection_date as prediction_anchor_date,
    boroughs.borough_name,
    latest.cuisine,
    latest.grade as previous_grade,
    latest.score as previous_score,
    latest.earlier_grade,
    latest.earlier_score,
    latest.score - latest.earlier_score as recent_score_change,
    latest.score > latest.earlier_score as latest_score_worsened,
    latest.days_between_last_two_graded_inspections,
    latest.recent_3_inspection_avg_score,
    latest.recent_3_critical_violation_count,
    latest.recent_3_inspections_with_critical,
    date_diff(
        'day', latest.inspection_date, cast('{{ scoring_date }}' as date)
    ) as days_since_last_graded_inspection,
    latest.violation_count as previous_inspection_violation_count,
    latest.critical_violation_count as previous_inspection_critical_violation_count,
    latest.has_critical_violation as previous_inspection_had_critical_violation,
    latest.known_graded_inspection_count,
    latest.historical_violation_count,
    latest.historical_critical_violation_count,
    latest.historical_grade_a_count,
    latest.historical_grade_b_count,
    latest.historical_grade_c_count,
    1.0 * latest.historical_grade_a_count
        / latest.known_graded_inspection_count as historical_grade_a_rate,
    (
        case when latest.historical_grade_a_count > 0 then 1 else 0 end
        + case when latest.historical_grade_b_count > 0 then 1 else 0 end
        + case when latest.historical_grade_c_count > 0 then 1 else 0 end
    ) = 1 as historical_grades_consistent,
    complaints.prior_90d_nearby_complaint_count,
    complaints.prior_90d_rodent_complaint_count,
    complaints.prior_90d_food_poisoning_complaint_count,
    complaints.prior_90d_food_establishment_complaint_count
from latest_history as latest
join {{ ref('dim_restaurant') }} as restaurants
    on latest.restaurant_key = restaurants.restaurant_key
left join {{ ref('dim_borough') }} as boroughs
    on latest.borough_key = boroughs.borough_key
join recent_complaints as complaints
    on latest.graded_inspection_key = complaints.graded_inspection_key
