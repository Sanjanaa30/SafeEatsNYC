select *
from {{ ref('dim_restaurant') }}
where is_chain <> (normalized_name_location_count >= 3)
   or (is_chain and chain_key is null)
   or (not is_chain and chain_key is not null)
