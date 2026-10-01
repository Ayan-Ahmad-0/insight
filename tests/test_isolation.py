import json
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def conn():
    c = psycopg.connect(os.environ["DATABASE_URL"])
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def orgs(conn):
    rows = conn.execute("select id from app.orgs order by name limit 2").fetchall()
    return rows[0][0], rows[1][0]


def as_tenant(conn, org_id, claim_key="app_metadata"):
    claims = {"sub": str(uuid.uuid4()), claim_key: {"org_id": str(org_id)}}
    conn.execute("select set_config('request.jwt.claims', %s, true)", [json.dumps(claims)])
    conn.execute("set local role authenticated")


def seed_call(conn, org_id, rid):
    conn.execute(
        "insert into ai.calls (org_id, request_id, question, status) "
        "values (%s, %s, 'q', 'ok')", [org_id, rid])


def test_rls_enabled_on_ai_tables(conn):
    rows = conn.execute(
        "select c.relname, c.relrowsecurity from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'ai' and c.relkind = 'r'").fetchall()
    assert {r[0] for r in rows} >= {"calls", "org_settings", "definitions"}
    assert all(r[1] for r in rows), rows


def test_tenant_sees_only_own_calls(conn, orgs):
    a, b = orgs
    seed_call(conn, a, "iso-a")
    seed_call(conn, b, "iso-b")
    as_tenant(conn, a)
    seen = {r[0] for r in conn.execute(
        "select request_id from ai.calls where request_id like 'iso-%'").fetchall()}
    assert seen == {"iso-a"}


def test_tenant_cannot_insert_call_for_other_org(conn, orgs):
    a, b = orgs
    as_tenant(conn, a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            seed_call(conn, b, "iso-forged")


def test_tenant_cannot_update_or_delete_calls(conn, orgs):
    a, _ = orgs
    seed_call(conn, a, "iso-a")
    as_tenant(conn, a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            conn.execute("update ai.calls set cost_usd = 0 where request_id = 'iso-a'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            conn.execute("delete from ai.calls where request_id = 'iso-a'")


def test_tenant_cannot_change_own_kill_switch_or_budget(conn, orgs):
    a, _ = orgs
    as_tenant(conn, a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            conn.execute("insert into ai.org_settings (org_id, daily_budget_usd) values (%s, 999)", [a])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.transaction():
            conn.execute("update ai.org_settings set daily_budget_usd = 999")


def test_tenant_sees_only_own_settings(conn, orgs):
    a, b = orgs
    conn.execute("insert into ai.org_settings (org_id, ai_enabled) values (%s, false), (%s, false) "
                 "on conflict (org_id) do update set ai_enabled = false", [a, b])
    as_tenant(conn, a)
    ids = {r[0] for r in conn.execute("select org_id from ai.org_settings").fetchall()}
    assert ids == {a}


def test_forged_user_metadata_sees_nothing(conn, orgs):
    a, _ = orgs
    seed_call(conn, a, "iso-a")
    as_tenant(conn, a, claim_key="user_metadata")      # not app_metadata: must be ignored
    n = conn.execute("select count(*) from ai.calls where request_id = 'iso-a'").fetchone()[0]
    assert n == 0