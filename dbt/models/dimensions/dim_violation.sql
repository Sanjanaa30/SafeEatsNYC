select
    to_hex(sha256(to_utf8(violation_code))) as violation_key,
    violation_code,
    max(violation_description) as violation_description,
    max(case when upper(critical_flag) = 'CRITICAL' then 1 else 0 end) = 1 as is_critical
from {{ ref('stg_inspections') }}
where violation_code is not null
group by violation_code
