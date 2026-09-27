with history_windows as (
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
        sum(violation_count) over (
            partition by restaurant_key
            order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_violation_count,
        sum(critical_violation_count) over (
            partition by restaurant_key
            order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_critical_violation_count,
        sum(case when grade = 'A' then 1 else 0 end) over (
            partition by restaurant_key
            order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_a_count,
        sum(case when grade = 'B' then 1 else 0 end) over (
            partition by restaurant_key
            order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_b_count,
        sum(case when grade = 'C' then 1 else 0 end) over (
            partition by restaurant_key
            order by inspection_date
            rows between unbounded preceding and current row
        ) as historical_grade_c_count
    from {{ ref('ml_graded_inspections') }} as inspections
),

labeled_history as (
    select
        targets.prediction_anchor_key,
        targets.target_inspection_key,
        targets.restaurant_key,
        targets.prediction_anchor_date,
        targets.target_inspection_date,
        targets.target_grade,
        targets.target_is_bc,
        history.borough_key,
        history.cuisine,
        history.latitude,
        history.longitude,
        history.grade as previous_grade,
        history.score as previous_score,
        history.earlier_grade,
        history.earlier_score,
        history.score - history.earlier_score as recent_score_change,
        history.score > history.earlier_score as latest_score_worsened,
        history.days_between_last_two_graded_inspections,
        history.recent_3_inspection_avg_score,
        history.recent_3_critical_violation_count,
        history.recent_3_inspections_with_critical,
        date_diff(
            'day',
            targets.prediction_anchor_date,
            targets.target_inspection_date
        ) as days_since_last_graded_inspection,
        history.violation_count as previous_inspection_violation_count,
        history.critical_violation_count as previous_inspection_critical_violation_count,
        history.has_critical_violation as previous_inspection_had_critical_violation,
        history.known_graded_inspection_count,
        history.historical_violation_count,
        history.historical_critical_violation_count,
        history.historical_grade_a_count,
        history.historical_grade_b_count,
        history.historical_grade_c_count,
        1.0 * history.historical_grade_a_count
            / history.known_graded_inspection_count as historical_grade_a_rate,
        (
            case when history.historical_grade_a_count > 0 then 1 else 0 end
            + case when history.historical_grade_b_count > 0 then 1 else 0 end
            + case when history.historical_grade_c_count > 0 then 1 else 0 end
        ) = 1 as historical_grades_consistent
    from {{ ref('ml_inspection_targets') }} as targets
    join history_windows as history
        on targets.prediction_anchor_key = history.graded_inspection_key
),

past_nearby_complaints as (
    select
        history.prediction_anchor_key,
        count(complaints.complaint_id) as prior_90d_nearby_complaint_count,
        sum(case when complaints.complaint_type = 'RODENT' then 1 else 0 end) as prior_90d_rodent_complaint_count,
        sum(case when complaints.complaint_type = 'FOOD POISONING' then 1 else 0 end) as prior_90d_food_poisoning_complaint_count,
        sum(case when complaints.complaint_type = 'FOOD ESTABLISHMENT' then 1 else 0 end) as prior_90d_food_establishment_complaint_count
    from labeled_history as history
    join {{ ref('dim_restaurant') }} as restaurants
        on history.restaurant_key = restaurants.restaurant_key
    left join {{ ref('stg_complaints') }} as complaints
        on complaints.restaurant_camis = restaurants.camis
        and complaints.restaurant_match_status = 'MATCHED'
        and complaints.created_date >= cast(
            date_add('day', -90, history.target_inspection_date) as timestamp
        )
        and complaints.created_date < cast(history.target_inspection_date as timestamp)
        and abs(complaints.restaurant_latitude - history.latitude) <= 0.000001
        and abs(complaints.restaurant_longitude - history.longitude) <= 0.000001
    group by history.prediction_anchor_key
)

select
    history.prediction_anchor_key,
    history.target_inspection_key,
    history.restaurant_key,
    restaurants.camis,
    history.prediction_anchor_date,
    history.target_inspection_date,
    history.target_grade,
    history.target_is_bc,
    history.borough_key,
    boroughs.borough_name,
    history.cuisine,
    history.previous_grade,
    history.previous_score,
    history.earlier_grade,
    history.earlier_score,
    history.recent_score_change,
    history.latest_score_worsened,
    history.days_between_last_two_graded_inspections,
    history.recent_3_inspection_avg_score,
    history.recent_3_critical_violation_count,
    history.recent_3_inspections_with_critical,
    history.days_since_last_graded_inspection,
    history.previous_inspection_violation_count,
    history.previous_inspection_critical_violation_count,
    history.previous_inspection_had_critical_violation,
    history.known_graded_inspection_count,
    history.historical_violation_count,
    history.historical_critical_violation_count,
    history.historical_grade_a_count,
    history.historical_grade_b_count,
    history.historical_grade_c_count,
    history.historical_grade_a_rate,
    history.historical_grades_consistent,
    complaints.prior_90d_nearby_complaint_count,
    complaints.prior_90d_rodent_complaint_count,
    complaints.prior_90d_food_poisoning_complaint_count,
    complaints.prior_90d_food_establishment_complaint_count
from labeled_history as history
join {{ ref('dim_restaurant') }} as restaurants
    on history.restaurant_key = restaurants.restaurant_key
left join {{ ref('dim_borough') }} as boroughs
    on history.borough_key = boroughs.borough_key
join past_nearby_complaints as complaints
    on history.prediction_anchor_key = complaints.prediction_anchor_key
