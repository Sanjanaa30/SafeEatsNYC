select
    to_hex(
        sha256(
            to_utf8(
                concat(
                    cast(facts.borough_key as varchar),
                    '||',
                    facts.violation_key
                )
            )
        )
    ) as violation_borough_key,
    facts.borough_key,
    boroughs.borough_name,
    facts.violation_key,
    violations.violation_code,
    violations.violation_description,
    violations.is_critical,
    case when violations.is_critical then 'CRITICAL' else 'NON_CRITICAL' end as criticality,
    count(*) as violation_count,
    count(distinct facts.inspection_id) as inspection_count,
    count(distinct facts.restaurant_key) as affected_restaurant_count,
    boroughs.total_restaurants,
    100.0 * count(*) / nullif(boroughs.total_restaurants, 0) as violations_per_100_restaurants
from {{ ref('fact_inspection') }} as facts
join {{ ref('dim_violation') }} as violations
    on facts.violation_key = violations.violation_key
join {{ ref('dim_borough') }} as boroughs
    on facts.borough_key = boroughs.borough_key
group by
    facts.borough_key,
    boroughs.borough_name,
    facts.violation_key,
    violations.violation_code,
    violations.violation_description,
    violations.is_critical,
    boroughs.total_restaurants
