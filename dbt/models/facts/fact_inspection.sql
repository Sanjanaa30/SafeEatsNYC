select
    inspections.inspection_violation_id as inspection_event_key,
    to_hex(
        sha256(
            to_utf8(
                concat_ws(
                    '||',
                    inspections.camis,
                    cast(inspections.inspection_date as varchar),
                    coalesce(inspections.inspection_type, '')
                )
            )
        )
    ) as inspection_id,
    to_hex(sha256(to_utf8(inspections.camis))) as restaurant_key,
    cast(date_format(cast(inspections.inspection_date as date), '%Y%m%d') as integer) as date_key,
    case
        when inspections.violation_code is not null
        then to_hex(sha256(to_utf8(inspections.violation_code)))
    end as violation_key,
    case inspections.borough
        when 'BRONX' then 1
        when 'BROOKLYN' then 2
        when 'MANHATTAN' then 3
        when 'QUEENS' then 4
        when 'STATEN ISLAND' then 5
    end as borough_key,
    inspections.score,
    inspections.grade,
    inspections.inspection_type,
    inspections.inspection_action,
    upper(inspections.critical_flag) = 'CRITICAL' as is_critical
from {{ ref('stg_inspections') }} as inspections
