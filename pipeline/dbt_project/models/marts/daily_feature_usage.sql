select
    org_id,
    (occurred_at at time zone 'UTC')::date as usage_date,
    feature,
    count(*)                 as event_count,
    count(distinct user_id)  as active_users
from {{ ref('stg_feature_events') }}
where (occurred_at at time zone 'UTC')::date < (now() at time zone 'UTC')::date
group by 1, 2, 3