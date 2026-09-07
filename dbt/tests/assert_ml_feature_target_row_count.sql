select 1
where
    (select count(*) from {{ ref('ml_training_features') }})
    <>
    (select count(*) from {{ ref('ml_inspection_targets') }})
