with changes as (
    select
        org_id, event_id, event_type, plan, mrr_cents, occurred_at,
        (occurred_at at time zone 'UTC')::date as effective_date,
        lead((occurred_at at time zone 'UTC')::date)
            over (partition by org_id order by occurred_at, event_id) as next_date
    from {{ ref('stg_subscription_events') }}
),
bounds as (
    select org_id, min(effective_date) as first_day from changes group by 1
),
spine as (
    select b.org_id, gs::date as mrr_date
    from bounds b
    cross join lateral generate_series(
        b.first_day::timestamp,
        ((now() at time zone 'UTC')::date - 1)::timestamp,
        interval '1 day') as gs
)
select
    s.org_id,
    s.mrr_date,
    c.plan,
    c.mrr_cents,
    case when c.event_type = 'canceled' then 'canceled' else 'active' end as status
from spine s
join changes c
  on c.org_id = s.org_id
 and s.mrr_date >= c.effective_date
 and (c.next_date is null or s.mrr_date < c.next_date)