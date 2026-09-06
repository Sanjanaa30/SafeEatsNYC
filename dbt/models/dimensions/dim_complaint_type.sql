select
    to_hex(sha256(to_utf8(complaint_type))) as complaint_type_key,
    complaint_type
from {{ ref('stg_complaints') }}
where complaint_type is not null
group by complaint_type
