with sequenced as (
    select
        *,
        lead(graded_inspection_key) over (
            partition by restaurant_key
            order by inspection_date
        ) as target_inspection_key,
        lead(inspection_date) over (
            partition by restaurant_key
            order by inspection_date
        ) as target_inspection_date,
        lead(grade) over (
            partition by restaurant_key
            order by inspection_date
        ) as target_grade
    from {{ ref('ml_graded_inspections') }}
)

select
    graded_inspection_key as prediction_anchor_key,
    restaurant_key,
    inspection_date as prediction_anchor_date,
    target_inspection_key,
    target_inspection_date,
    target_grade,
    case when target_grade in ('B', 'C') then 1 else 0 end as target_is_bc
from sequenced
where target_inspection_key is not null
  and target_inspection_date > inspection_date
