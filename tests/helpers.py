import os, json
from contextlib import contextmanager
import psycopg
from dotenv import load_dotenv

load_dotenv()
DSN = os.environ["DATABASE_URL"]

# table -> column holding the tenant id
TENANT_TABLES = {
    "app.orgs": "id",
    "app.org_members": "org_id",
    "raw.feature_events": "org_id",
    "raw.subscription_events": "org_id",
    "analytics.daily_feature_usage": "org_id",
    "analytics.daily_org_activity": "org_id",
    "analytics.mrr_daily": "org_id",
    "analytics.morning_digest": "org_id",
}


def org_claims(org_id):
    return {"app_metadata": {"org_id": str(org_id)}}


@contextmanager
def as_tenant(claims):
    """Open a transaction that behaves like an API request with these JWT claims."""
    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()
        cur.execute("select set_config('request.jwt.claims', %s, true)", [json.dumps(claims)])
        cur.execute("set local role authenticated")
        try:
            yield cur
        finally:
            conn.rollback()