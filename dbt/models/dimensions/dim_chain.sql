select
    chain_key,
    restaurant_name_normalized as chain_name,
    count(distinct camis) as location_count,
    count(distinct borough) as borough_count,
    max(case when is_confirmed_fast_food then 1 else 0 end) = 1 as is_confirmed_fast_food
from {{ ref('stg_chain_flags') }}
where is_chain
group by chain_key, restaurant_name_normalized
