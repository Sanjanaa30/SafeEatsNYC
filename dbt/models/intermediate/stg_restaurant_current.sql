with ranked_restaurants as (
    select
        *,
        row_number() over (
            partition by camis
            order by inspection_date desc, inspection_violation_id desc
        ) as restaurant_row_number
    from {{ ref('stg_inspections') }}
    where camis is not null
)

select
    camis,
    restaurant_name,
    restaurant_name_normalized,
    address,
    zipcode,
    cuisine,
    borough,
    latitude,
    longitude,
    coordinate_status,
    fast_food_brand_names,
    is_reviewed_co_brand,
    is_confirmed_fast_food
from ranked_restaurants
where restaurant_row_number = 1
