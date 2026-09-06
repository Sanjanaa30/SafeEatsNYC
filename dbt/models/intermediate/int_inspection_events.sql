select
    inspection_id,
    restaurant_key,
    date_key,
    borough_key,
    max(score) as score,
    max(grade) as grade,
    max(inspection_type) as inspection_type,
    count(violation_key) as violation_count,
    sum(case when is_critical then 1 else 0 end) as critical_violation_count,
    max(case when is_critical then 1 else 0 end) = 1 as has_critical_violation
from {{ ref('fact_inspection') }}
group by inspection_id, restaurant_key, date_key, borough_key
