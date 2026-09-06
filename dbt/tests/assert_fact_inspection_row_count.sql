select 1
where
    (select count(*) from {{ ref('fact_inspection') }})
    <>
    (select count(*) from {{ ref('stg_inspections') }})
