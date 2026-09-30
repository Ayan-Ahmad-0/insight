import datetime as dt

FEATURE_SQL = """
insert into raw.feature_events(org_id, user_id, feature, occurred_at, event_key)
values (%s, %s, %s, %s, %s)
on conflict (org_id, event_key) do nothing
"""

SUB_SQL = """
insert into raw.subscription_events(org_id, event_type, plan, mrr_cents, occurred_at, event_key)
values (%s, %s, %s, %s, %s, %s)
on conflict (org_id, event_key) do nothing
"""


def _not_future(ts):
    return ts <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)


def ingest_feature_events(conn, rows):
    """rows: (org_id, user_id, feature, occurred_at, event_key). Returns (inserted, rejected)."""
    good = [r for r in rows if r[2] and _not_future(r[3])]
    inserted = 0
    if good:
        with conn.cursor() as cur:
            cur.executemany(FEATURE_SQL, good)
            inserted = max(cur.rowcount, 0)
    return inserted, len(rows) - len(good)


def ingest_subscription_events(conn, rows):
    """rows: (org_id, event_type, plan, mrr_cents, occurred_at, event_key)."""
    good = [r for r in rows if _not_future(r[4])]
    inserted = 0
    if good:
        with conn.cursor() as cur:
            cur.executemany(SUB_SQL, good)
            inserted = max(cur.rowcount, 0)
    return inserted, len(rows) - len(good)


def log_run(conn, source, received, inserted, rejected, status="ok", error=None):
    conn.execute(
        "insert into raw.ingest_runs(source, finished_at, rows_received, rows_inserted,"
        " rows_rejected, status, error) values (%s, now(), %s, %s, %s, %s, %s)",
        [source, received, inserted, rejected, status, error])