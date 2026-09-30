select 1 as problem
where not exists (
    select 1 from {{ ref('daily_feature_usage') }}
    where usage_date = (now() at time zone 'UTC')::date - 1
)