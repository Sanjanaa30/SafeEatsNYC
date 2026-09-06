with restaurants as (
    select * from {{ ref('stg_restaurant_current') }}
),

name_location_counts as (
    select
        restaurant_name_normalized,
        count(distinct camis) as location_count
    from restaurants
    where restaurant_name_normalized is not null
    group by restaurant_name_normalized
)

select
    restaurants.*,
    coalesce(name_location_counts.location_count, 1) as normalized_name_location_count,
    coalesce(name_location_counts.location_count >= 3, false) as is_chain,
    case
        when name_location_counts.location_count >= 3
        then to_hex(sha256(to_utf8(restaurants.restaurant_name_normalized)))
    end as chain_key
from restaurants
left join name_location_counts
    on restaurants.restaurant_name_normalized = name_location_counts.restaurant_name_normalized
