with graded_rows as (
    select
        facts.inspection_event_key,
        facts.inspection_id,
        facts.restaurant_key,
        facts.date_key,
        dates.calendar_date as inspection_date,
        facts.borough_key,
        staging.cuisine,
        staging.latitude,
        staging.longitude,
        facts.grade,
        facts.score,
        facts.violation_key,
        facts.is_critical
    from {{ ref('fact_inspection') }} as facts
    join {{ ref('stg_inspections') }} as staging
        on facts.inspection_event_key = staging.inspection_violation_id
    join {{ ref('dim_date') }} as dates
        on facts.date_key = dates.date_key
    where facts.grade in ('A', 'B', 'C')
)

select
    to_hex(
        sha256(
            to_utf8(
                concat(
                    restaurant_key,
                    '||',
                    cast(inspection_date as varchar)
                )
            )
        )
    ) as graded_inspection_key,
    restaurant_key,
    date_key,
    inspection_date,
    max(borough_key) as borough_key,
    max(cuisine) as cuisine,
    max(latitude) as latitude,
    max(longitude) as longitude,
    max(grade) as grade,
    max(score) as score,
    count(distinct inspection_id) as source_inspection_event_count,
    count(violation_key) as violation_count,
    sum(case when is_critical then 1 else 0 end) as critical_violation_count,
    max(case when is_critical then 1 else 0 end) = 1 as has_critical_violation
from graded_rows
group by restaurant_key, date_key, inspection_date
