select 1
where
    (select count(*) from {{ ref('fact_311_complaint') }})
    <>
    (select count(*) from {{ ref('stg_complaints') }})
