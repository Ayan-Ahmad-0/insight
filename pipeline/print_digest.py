import psycopg
from common import DSN

SQL = """
select o.name, d.active_users, d.avg_active_same_weekday, d.events, d.top_feature,
       d.plan, d.mrr_cents / 100.0 as mrr, d.flag_usage_drop, d.flag_usage_spike, d.flag_canceled
from analytics.morning_digest d
join app.orgs o on o.id = d.org_id
where d.digest_date = (now() at time zone 'UTC')::date - 1
order by d.flag_usage_drop desc, d.flag_canceled desc, d.flag_usage_spike desc, d.mrr_cents desc
limit %s
"""

with psycopg.connect(DSN) as conn:
    print(f"{'org':28} {'act':>4} {'avg':>5} {'evts':>5} {'top feature':14} {'plan':8} {'mrr':>8}  flags")
    for n, a, avg, e, tf, plan, mrr, drop, spike, canc in conn.execute(SQL, [15]).fetchall():
        flags = " ".join(f for f, on in [("DROP", drop), ("SPIKE", spike), ("CANCELED", canc)] if on)
        print(f"{n[:27]:28} {a:>4} {avg or 0:>5} {e:>5} {tf or '-':14} {plan or '-':8} {mrr or 0:>8.0f}  {flags}")