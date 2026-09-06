select dimensions.camis
from {{ ref('dim_restaurant') }} as dimensions
join {{ ref('stg_restaurant_current') }} as staging
    on dimensions.camis = staging.camis
where dimensions.is_confirmed_fast_food <> staging.is_confirmed_fast_food
   or dimensions.is_reviewed_co_brand <> staging.is_reviewed_co_brand
   or dimensions.fast_food_brand_names <> staging.fast_food_brand_names
