import os

import psycopg

PLANS = ["starter", "growth", "scale"]

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    for i in range(6):
        org_id = conn.execute(
            "insert into app.orgs (name, plan) values (%s, %s) returning id",
            [f"CI Org {i + 1}", PLANS[i % 3]]).fetchone()[0]
        for u in range(2):
            uid = conn.execute(
                "insert into auth.users (email) values (%s) returning id",
                [f"user{u + 1}@ci-org{i + 1}.test"]).fetchone()[0]
            conn.execute(
                "insert into app.org_members (org_id, user_id, role) values (%s, %s, %s)",
                [org_id, uid, "admin" if u == 0 else "member"])
        conn.execute(
            "insert into raw.subscription_events "
            "(org_id, event_type, plan, mrr_cents, occurred_at, event_key) "
            "values (%s, 'started', %s, 4900, now() - interval '40 days', 'ci-start')",
            [org_id, PLANS[i % 3]])
    conn.commit()
print("seeded 6 CI orgs")