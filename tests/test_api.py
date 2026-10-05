import base64, datetime as dt, json, os, pathlib, sys, time, uuid
import httpx, jwt as pyjwt, psycopg, pytest
from fastapi.testclient import TestClient

from helpers import DSN                      # loads .env first

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
from app.main import app                     # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"]


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _login(email):
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
        json={"email": email, "password": os.environ["SEED_PASSWORD"]}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def orgs():
    with psycopg.connect(DSN) as conn:
        rows = conn.execute("""
            select distinct on (m.org_id) m.org_id, u.email
            from app.org_members m
            join app.orgs o on o.id = m.org_id
            join auth.users u on u.id = m.user_id
            join analytics.morning_digest d on d.org_id = m.org_id
            where o.data_source = 'synthetic'
            order by m.org_id, u.email""").fetchall()
    (a_id, a_mail), (b_id, b_mail) = rows[0], rows[1]
    return {"A": {"id": a_id, "token": _login(a_mail)},
            "B": {"id": b_id, "token": _login(b_mail)}}


def _default_range():
    to = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    return to - dt.timedelta(days=29), to


def _db_events(org, frm, to):
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "select coalesce(sum(events), 0) from analytics.daily_org_activity"
            " where org_id = %s and usage_date between %s and %s", [org, frm, to]).fetchone()[0]


def test_me_returns_callers_own_org(client, orgs):
    for k in ("A", "B"):
        r = client.get("/v1/me", headers=H(orgs[k]["token"]))
        assert r.status_code == 200
        assert r.json()["org_id"] == str(orgs[k]["id"])


def test_usage_matches_database_truth_per_org(client, orgs):
    frm, to = _default_range()
    for k in ("A", "B"):
        r = client.get("/v1/usage/daily", headers=H(orgs[k]["token"]))
        assert r.status_code == 200
        assert sum(d["events"] for d in r.json()) == _db_events(orgs[k]["id"], frm, to)


@pytest.mark.parametrize("path", ["/v1/me", "/v1/digest", "/v1/usage/daily",
                                  "/v1/usage/features", "/v1/revenue/mrr"])
def test_spoofed_org_parameters_are_ignored(client, orgs, path):
    a, b = orgs["A"], orgs["B"]
    plain = client.get(path, headers=H(a["token"]))
    spoof = client.get(path, params={"org_id": str(b["id"])},
                       headers={**H(a["token"]), "X-Org-Id": str(b["id"])})
    assert plain.status_code == spoof.status_code == 200
    assert spoof.json() == plain.json()


def test_missing_or_garbage_token_is_401(client):
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers=H("garbage")).status_code == 401


def test_tampered_payload_is_401(client, orgs):
    head, payload, sig = orgs["A"]["token"].split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    data["app_metadata"]["org_id"] = str(orgs["B"]["id"])
    forged = f"{head}.{_b64(data)}.{sig}"
    assert client.get("/v1/me", headers=H(forged)).status_code == 401


def _claims_for(org):
    return {"sub": str(uuid.uuid4()), "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1", "exp": int(time.time()) + 300,
            "app_metadata": {"org_id": str(org)}}


def test_token_signed_with_attackers_key_is_401(client, orgs):
    forged = pyjwt.encode(_claims_for(orgs["B"]["id"]), "x" * 64, algorithm="HS256")
    assert client.get("/v1/me", headers=H(forged)).status_code == 401


def test_alg_none_token_is_401(client, orgs):
    token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(_claims_for(orgs['B']['id']))}."
    assert client.get("/v1/me", headers=H(token)).status_code == 401


def test_event_ingest_is_scoped_to_callers_org_and_idempotent(client, orgs):
    a = orgs["A"]
    key = f"apitest-{uuid.uuid4()}"
    body = {"events": [{"feature": "reports", "event_key": key,
                        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat()}]}
    first = client.post("/v1/events", json=body, headers=H(a["token"]))
    assert first.status_code == 200 and first.json()["inserted"] == 1
    again = client.post("/v1/events", json=body, headers=H(a["token"]))
    assert again.json() == {"received": 1, "inserted": 0, "duplicates": 1}
    with psycopg.connect(DSN) as conn:
        row = conn.execute("select org_id from raw.feature_events where event_key = %s",
                           [key]).fetchone()
        assert row[0] == a["id"]
        conn.execute("delete from raw.feature_events where event_key = %s", [key])
        conn.commit()


def test_event_body_cannot_name_an_org(client, orgs):
    body = {"events": [{"org_id": str(orgs["B"]["id"]), "feature": "reports",
                        "event_key": "abcdefgh12",
                        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat()}]}
    assert client.post("/v1/events", json=body, headers=H(orgs["A"]["token"])).status_code == 422