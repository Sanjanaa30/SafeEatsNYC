select
    to_hex(sha256(to_utf8(restaurants.camis))) as restaurant_key,
    restaurants.camis,
    restaurants.restaurant_name,
    restaurants.restaurant_name_normalized,
    restaurants.address,
    restaurants.zipcode,
    zip_lookup.nta_code,
    zip_lookup.nta_name,
    case restaurants.borough
        when 'BRONX' then 1
        when 'BROOKLYN' then 2
        when 'MANHATTAN' then 3
        when 'QUEENS' then 4
        when 'STATEN ISLAND' then 5
    end as borough_key,
    restaurants.cuisine,
    restaurants.latitude,
    restaurants.longitude,
    restaurants.coordinate_status,
    restaurants.normalized_name_location_count,
    restaurants.is_chain,
    restaurants.is_confirmed_fast_food,
    restaurants.is_reviewed_co_brand,
    restaurants.fast_food_brand_names,
    restaurants.chain_key,
    restaurants.chain_family_name,
    restaurants.chain_match_method,
    restaurants.chain_match_confidence,
    true as is_current
from {{ ref('stg_chain_flags') }} as restaurants
left join {{ ref('zip_to_nta') }} as zip_lookup
    on restaurants.zipcode = zip_lookup.zip
