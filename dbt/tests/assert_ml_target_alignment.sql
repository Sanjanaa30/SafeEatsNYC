select prediction_anchor_key
from {{ ref('ml_inspection_targets') }}
where target_inspection_date <= prediction_anchor_date
   or target_is_bc <> case when target_grade in ('B', 'C') then 1 else 0 end
