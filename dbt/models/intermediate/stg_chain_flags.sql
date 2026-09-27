with restaurants as (
    select * from {{ ref('stg_restaurant_current') }}
),

exact_name_counts as (
    select
        restaurant_name_normalized,
        count(distinct camis) as exact_location_count
    from restaurants
    where restaurant_name_normalized is not null
    group by restaurant_name_normalized
),

anchor_cuisines as (
    select distinct
        restaurants.restaurant_name_normalized as anchor_name,
        restaurants.cuisine
    from restaurants
    join exact_name_counts
      on restaurants.restaurant_name_normalized
       = exact_name_counts.restaurant_name_normalized
    where exact_name_counts.exact_location_count >= 3
      and length(restaurants.restaurant_name_normalized) >= 5
),

variant_candidates as (
    select
        restaurants.camis,
        anchors.anchor_name,
        row_number() over (
            partition by restaurants.camis
            order by length(anchors.anchor_name) desc, anchors.anchor_name
        ) as candidate_rank
    from restaurants
    join anchor_cuisines as anchors
      on restaurants.cuisine = anchors.cuisine
     and restaurants.restaurant_name_normalized
         like concat(anchors.anchor_name, ' %')
    where not restaurants.is_reviewed_co_brand
      and cardinality(split(restaurants.restaurant_name_normalized, ' '))
          <= cardinality(split(anchors.anchor_name, ' ')) + 2
),

assigned_families as (
    select
        restaurants.*,
        coalesce(
            variants.anchor_name,
            restaurants.restaurant_name_normalized
        ) as detected_chain_family_name,
        case
            when exact_counts.exact_location_count >= 3 then 'EXACT_NAME'
            when variants.anchor_name is not null then 'AUTO_PREFIX'
            else 'UNMATCHED'
        end as detected_chain_match_method
    from restaurants
    left join exact_name_counts as exact_counts
      on restaurants.restaurant_name_normalized
       = exact_counts.restaurant_name_normalized
    left join variant_candidates as variants
      on restaurants.camis = variants.camis
     and variants.candidate_rank = 1
),

family_location_counts as (
    select
        detected_chain_family_name,
        count(distinct camis) as location_count
    from assigned_families
    where detected_chain_family_name is not null
    group by detected_chain_family_name
)

select
    restaurants.*,
    coalesce(families.location_count, 1) as normalized_name_location_count,
    coalesce(families.location_count >= 3, false) as is_chain,
    case
        when families.location_count >= 3
        then to_hex(sha256(to_utf8(restaurants.detected_chain_family_name)))
    end as chain_key,
    case
        when families.location_count >= 3
        then restaurants.detected_chain_family_name
    end as chain_family_name,
    case
        when families.location_count >= 3
        then restaurants.detected_chain_match_method
        else 'UNMATCHED'
    end as chain_match_method,
    case
        when families.location_count >= 3
         and restaurants.detected_chain_match_method in ('EXACT_NAME', 'AUTO_PREFIX')
        then 'HIGH'
        else 'NONE'
    end as chain_match_confidence
from assigned_families as restaurants
left join family_location_counts as families
  on restaurants.detected_chain_family_name
   = families.detected_chain_family_name
