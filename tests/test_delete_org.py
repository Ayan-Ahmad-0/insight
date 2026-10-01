import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from delete_org import DeleteError, delete_org, inventory  # noqa: E402

load_dotenv()


@pytest.fixture
def conn():
    c = psycopg.connect(os.environ["DATABASE_URL"])
    yield c
    c.close()


def create_auth_user(email, org_id):
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    body = json.dumps({"email": email, "password": uuid.uuid4().hex + "Aa1!",
                       "email_confirm": True, "app_metadata": {"org_id": str(org_id)}}).encode()
    req = urllib.request.Request(
        f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users", data=body, method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["id"]


@pytest.fixture
def throwaway(conn):
    name = f"zz-delete-test-{uuid.uuid4().hex[:8]}"
    org_id = conn.execute("insert into app.orgs (name) values (%s) returning id", [name]).fetchone()[0]
    uid = create_auth_user(f"{name}@example.test", org_id)
    conn.execute("insert into app.org_members (org_id, user_id, role) values (%s, %s, 'admin')",
                 [org_id, uid])
    for i in range(3):
        conn.execute(
            "insert into raw.feature_events (org_id, user_id, feature, occurred_at, event_key) "
            "values (%s, %s, 'billing', now() - interval '1 day', %s)", [org_id, uid, f"k{i}"])
    conn.execute(
        "insert into raw.subscription_events (org_id, event_type, plan, mrr_cents, occurred_at, event_key) "
        "values (%s, 'started', 'starter', 4900, now() - interval '30 days', 's1')", [org_id])
    conn.execute(
        "insert into ai.calls (org_id, user_id, request_id, question, status) "
        "values (%s, %s, 'del-test', 'q', 'ok')", [org_id, uid])
    conn.execute(  # dbt mart row: no foreign key, so this proves the explicit delete path
        "insert into analytics.daily_org_activity "
        "(org_id, usage_date, events, active_users, weekly_active_users) "
        "values (%s, current_date - 1, 3, 1, 1)", [org_id])
    conn.commit()
    yield org_id, name, uid
    try:   # cleanup if a test failed halfway
        delete_org(org_id, execute=True, confirm_name=name)
    except DeleteError:
        pass


def test_dry_run_changes_nothing(conn, throwaway):
    org_id, name, _ = throwaway
    before = inventory(conn, org_id)
    out = delete_org(org_id)
    assert out["dry_run"] is True
    assert inventory(conn, org_id) == before


def test_wrong_confirmation_refuses(conn, throwaway):
    org_id, name, _ = throwaway
    with pytest.raises(DeleteError):
        delete_org(org_id, execute=True, confirm_name="not the name")
    assert inventory(conn, org_id)["app.orgs"] == 1


def test_full_delete_leaves_nothing_and_touches_no_one_else(conn, throwaway):
    org_id, name, uid = throwaway
    other = conn.execute("select id from app.orgs where id <> %s order by name limit 1",
                         [org_id]).fetchone()[0]
    other_before = inventory(conn, other)
    before = inventory(conn, org_id)
    assert before["raw.feature_events"] == 3 and before["ai.calls"] == 1
    assert before["analytics.daily_org_activity"] == 1

    receipt = delete_org(org_id, execute=True, confirm_name=name)

    assert receipt["status"] == "complete"
    assert all(v == 0 for v in receipt["rows_after"].values())
    assert "analytics.daily_org_activity" in receipt["tables_scanned"]
    assert "ai.calls" in receipt["tables_scanned"]
    assert all(v == 0 for v in inventory(conn, org_id).values())
    assert conn.execute("select count(*) from auth.users where id = %s", [uid]).fetchone()[0] == 0
    assert inventory(conn, other) == other_before          # no collateral damage
    assert Path(receipt["receipt_path"]).exists()


def test_cannot_write_to_deleted_org(conn, throwaway):
    org_id, name, _ = throwaway
    delete_org(org_id, execute=True, confirm_name=name)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(
            "insert into raw.feature_events (org_id, feature, occurred_at, event_key) "
            "values (%s, 'billing', now(), 'late')", [org_id])
    conn.rollback()