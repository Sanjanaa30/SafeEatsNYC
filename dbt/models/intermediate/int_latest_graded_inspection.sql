with ranked as (
    select
        *,
        row_number() over (
            partition by restaurant_key
            order by date_key desc, inspection_id desc
        ) as inspection_recency_rank
    from {{ ref('int_inspection_events') }}
    where grade in ('A', 'B', 'C')
)

select *
from ranked
where inspection_recency_rank = 1
