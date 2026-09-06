select
    complaints.complaint_id,
    case
        when complaints.restaurant_camis is not null
        then to_hex(sha256(to_utf8(complaints.restaurant_camis)))
    end as restaurant_key,
    cast(date_format(cast(complaints.created_date as date), '%Y%m%d') as integer) as date_key,
    to_hex(sha256(to_utf8(complaints.complaint_type))) as complaint_type_key,
    case upper(complaints.borough)
        when 'BRONX' then 1
        when 'BROOKLYN' then 2
        when 'MANHATTAN' then 3
        when 'QUEENS' then 4
        when 'STATEN ISLAND' then 5
    end as borough_key,
    complaints.created_date,
    complaints.closed_date,
    complaints.status,
    complaints.descriptor,
    complaints.location_type,
    complaints.incident_zip,
    complaints.incident_address,
    complaints.latitude,
    complaints.longitude,
    complaints.restaurant_match_status,
    complaints.match_distance_meters,
    complaints.match_threshold_meters
from {{ ref('stg_complaints') }} as complaints
