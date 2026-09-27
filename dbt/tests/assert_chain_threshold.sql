select *
from {{ ref('dim_restaurant') }}
where is_chain <> (normalized_name_location_count >= 3)
   or (is_chain and chain_key is null)
   or (not is_chain and chain_key is not null)
   or (is_chain and chain_family_name is null)
   or (is_chain and chain_match_confidence <> 'HIGH')
