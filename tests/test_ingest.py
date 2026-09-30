import sys, pathlib, uuid, datetime as dt
import pytest, psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))
from ingest import ingest_feature_events
from helpers import DSN, as_tenant, org_claims


def test_ingest_is_idempotent_and_rejects_future_events(truth):
    orgs, _ = truth
    now = dt.datetime.now(dt.timezone.utc)
    ok = (orgs[0], None, "reports", now - dt.timedelta(hours=1), f"test-{uuid.uuid4()}")
    future = (orgs[0], None, "reports", now + dt.timedelta(days=1), f"test-{uuid.uuid4()}")
    with psycopg.connect(DSN) as conn:
        assert ingest_feature_events(conn, [ok]) == (1, 0)
        assert ingest_feature_events(conn, [ok]) == (0, 0)        # same key: no duplicate
        assert ingest_feature_events(conn, [future]) == (0, 1)    # rejected
        conn.rollback()


def test_tenant_can_insert_own_event_but_not_read_ingest_log(truth):
    orgs, _ = truth
    with as_tenant(org_claims(orgs[0])) as cur:
        cur.execute(
            "insert into raw.feature_events(org_id, feature, occurred_at, event_key)"
            " values (%s, 'reports', now(), %s)", [orgs[0], f"t-{uuid.uuid4()}"])
        assert cur.rowcount == 1
    with as_tenant(org_claims(orgs[0])) as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select count(*) from raw.ingest_runs")