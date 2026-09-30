with activity as (
    select
        org_id,
        usage_date as digest_date,
        events,
        active_users,
        weekly_active_users,
        avg(active_users) over w as avg_active_same_weekday,
        avg(events)       over w as avg_events_same_weekday
    from {{ ref('daily_org_activity') }}
    window w as (
        partition by org_id, extract(dow from usage_date)
        order by usage_date
        rows between 4 preceding and 1 preceding
    )
),
top_feature as (
    select org_id, usage_date, feature as top_feature
    from (
        select org_id, usage_date, feature,
               row_number() over (partition by org_id, usage_date
                                  order by event_count desc, feature) as rn
        from {{ ref('daily_feature_usage') }}
    ) t
    where rn = 1
),
mrr as (
    select org_id, mrr_date, plan, status, mrr_cents,
           lag(mrr_cents, 7) over (partition by org_id order by mrr_date) as mrr_cents_7d_ago
    from {{ ref('mrr_daily') }}
)
select
    a.org_id,
    a.digest_date,
    a.events,
    a.active_users,
    a.weekly_active_users,
    round(a.avg_active_same_weekday::numeric, 1)  as avg_active_same_weekday,
    tf.top_feature,
    m.plan,
    m.status,
    m.mrr_cents,
    m.mrr_cents - m.mrr_cents_7d_ago              as mrr_change_7d_cents,
    (a.avg_active_same_weekday >= 3
       and a.active_users < 0.5 * a.avg_active_same_weekday)   as flag_usage_drop,
    (a.avg_events_same_weekday >= 10
       and a.events > 3 * a.avg_events_same_weekday)           as flag_usage_spike,
    (m.status = 'canceled')                                    as flag_canceled
from activity a
left join top_feature tf on tf.org_id = a.org_id and tf.usage_date = a.digest_date
left join mrr m          on m.org_id  = a.org_id and m.mrr_date   = a.digest_date