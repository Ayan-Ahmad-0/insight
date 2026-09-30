with user_days as (
    select distinct org_id, user_id, (occurred_at at time zone 'UTC')::date as usage_date
    from {{ ref('stg_feature_events') }}
    where user_id is not null
      and (occurred_at at time zone 'UTC')::date < (now() at time zone 'UTC')::date
),
daily as (
    select org_id, usage_date,
           sum(event_count) as events
    from {{ ref('daily_feature_usage') }}
    group by 1, 2
),
daily_users as (
    select org_id, usage_date, count(*) as active_users
    from user_days
    group by 1, 2
),
bounds as (
    select org_id, min(usage_date) as first_day from daily group by 1
),
spine as (
    select b.org_id, gs::date as usage_date
    from bounds b
    cross join lateral generate_series(
        b.first_day::timestamp,
        ((now() at time zone 'UTC')::date - 1)::timestamp,
        interval '1 day') as gs
),
wau as (
    select s.org_id, s.usage_date, count(distinct ud.user_id) as weekly_active_users
    from spine s
    left join user_days ud
      on ud.org_id = s.org_id
     and ud.usage_date between s.usage_date - 6 and s.usage_date
    group by 1, 2
)
select
    s.org_id,
    s.usage_date,
    coalesce(d.events, 0)        as events,
    coalesce(u.active_users, 0)  as active_users,
    w.weekly_active_users
from spine s
left join daily d       using (org_id, usage_date)
left join daily_users u using (org_id, usage_date)
join wau w              using (org_id, usage_date)