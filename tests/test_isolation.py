import pytest, psycopg
from helpers import as_tenant, org_claims, TENANT_TABLES


def test_each_tenant_sees_exactly_its_own_rows(truth):
    orgs, counts = truth
    for org in orgs:
        with as_tenant(org_claims(org)) as cur:
            for table, col in TENANT_TABLES.items():
                total = cur.execute(f"select count(*) from {table}").fetchone()[0]
                foreign = cur.execute(
                    f"select count(*) from {table} where {col} <> %s", [org]).fetchone()[0]
                assert foreign == 0, f"{table}: org {org} saw foreign rows"
                assert total == counts[table].get(org, 0), f"{table}: wrong count for {org}"


def test_no_org_claim_sees_nothing():
    with as_tenant({}) as cur:
        for table in TENANT_TABLES:
            assert cur.execute(f"select count(*) from {table}").fetchone()[0] == 0


def test_user_metadata_org_is_ignored(truth):
    orgs, _ = truth
    forged = {"user_metadata": {"org_id": str(orgs[0])}}   # user-editable in Supabase
    with as_tenant(forged) as cur:
        for table in TENANT_TABLES:
            assert cur.execute(f"select count(*) from {table}").fetchone()[0] == 0


def test_cannot_write_into_another_org(truth):
    orgs, _ = truth
    with as_tenant(org_claims(orgs[0])) as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into raw.feature_events(org_id, feature, occurred_at, event_key)"
                " values (%s, 'x', now(), 'hack')", [orgs[1]])


def test_tenant_cannot_read_auth_users(truth):
    orgs, _ = truth
    with as_tenant(org_claims(orgs[0])) as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select id from auth.users")