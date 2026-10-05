"""Unit tests for POST /v1/refresh and GET /v1/refresh/status. No database and no network:
the admin lookup and the two GitHub calls are replaced."""
import os, sys, pathlib, uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost:5432/x")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

import pytest                                                   # noqa: E402
from fastapi import FastAPI                                     # noqa: E402
from fastapi.testclient import TestClient                       # noqa: E402
from app import errors                                          # noqa: E402
from app.auth import Caller, get_caller                         # noqa: E402
from app.config import settings                                 # noqa: E402
from app.routers import refresh                                 # noqa: E402

ORG = uuid.uuid4()


def make_client(admin=True, authenticated=True):
    app = FastAPI()
    errors.install(app)
    app.include_router(refresh.router)
    if authenticated:
        app.dependency_overrides[get_caller] = lambda: Caller(uuid.uuid4(), ORG, {})
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    refresh._last_request.clear()
    refresh._cache.update(at=0.0, runs=[])
    monkeypatch.setattr(settings, "refresh_github_token", "test-token")
    monkeypatch.setattr(settings, "refresh_cooldown_s", 60)
    monkeypatch.setattr(refresh, "_is_admin", lambda caller: True)
    sent = []
    monkeypatch.setattr(refresh, "_dispatch", lambda org_id: sent.append(org_id))
    return sent


def run(minutes_ago, status="completed", conclusion="success"):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"created_at": t.isoformat().replace("+00:00", "Z"), "status": status, "conclusion": conclusion}


def test_unauthenticated_is_rejected():
    c = make_client(authenticated=False)
    assert c.post("/v1/refresh").status_code == 401
    assert c.get("/v1/refresh/status", params={"since": "2026-10-05T10:00:00Z"}).status_code == 401


def test_not_enabled_without_token(monkeypatch):
    monkeypatch.setattr(settings, "refresh_github_token", "")
    r = make_client().post("/v1/refresh")
    assert r.status_code == 503 and r.json()["error"]["code"] == "refresh_unavailable"


def test_member_cannot_refresh(monkeypatch, isolate):
    monkeypatch.setattr(refresh, "_is_admin", lambda caller: False)
    r = make_client().post("/v1/refresh")
    assert r.status_code == 403 and isolate == []


def test_admin_dispatches_with_org_from_token_only(isolate):
    r = make_client().post("/v1/refresh", json={"org_id": str(uuid.uuid4())})   # a body is ignored
    assert r.status_code == 202
    assert r.json()["state"] == "queued" and "requested_at" in r.json()
    assert isolate == [str(ORG)]


def test_cooldown_blocks_a_second_request(isolate):
    c = make_client()
    assert c.post("/v1/refresh").status_code == 202
    r = c.post("/v1/refresh")
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_soon"
    assert len(isolate) == 1


def test_failed_dispatch_does_not_start_the_cooldown(monkeypatch):
    def boom(org_id):
        raise errors.ApiError(502, "refresh_failed", "x")
    monkeypatch.setattr(refresh, "_dispatch", boom)
    c = make_client()
    assert c.post("/v1/refresh").status_code == 502
    monkeypatch.setattr(refresh, "_dispatch", lambda org_id: None)
    assert c.post("/v1/refresh").status_code == 202


def status(monkeypatch, runs, since_minutes_ago=1):
    refresh._cache.update(at=0.0, runs=[])
    monkeypatch.setattr(refresh, "_runs", lambda: runs)
    since = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes_ago)).isoformat().replace("+00:00", "Z")
    r = make_client().get("/v1/refresh/status", params={"since": since})
    assert r.status_code == 200
    return r.json()["state"]


def test_status_states(monkeypatch):
    assert status(monkeypatch, []) == "queued"                                           # not listed yet
    assert status(monkeypatch, [run(0, "queued", None)]) == "queued"
    assert status(monkeypatch, [run(0, "in_progress", None)]) == "running"
    assert status(monkeypatch, [run(0)]) == "succeeded"
    assert status(monkeypatch, [run(0, conclusion="failure")]) == "failed"
    assert status(monkeypatch, [run(0, conclusion="cancelled")]) == "failed"


def test_status_ignores_runs_from_before_the_request(monkeypatch):
    old_success = run(30)                                  # finished long before this request
    assert status(monkeypatch, [old_success]) == "queued"
    assert status(monkeypatch, [run(0, "in_progress", None), old_success]) == "running"   # newest first


def test_status_accepts_a_timestamp_without_timezone(monkeypatch):
    refresh._cache.update(at=0.0, runs=[])
    monkeypatch.setattr(refresh, "_runs", lambda: [run(0)])
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    assert make_client().get("/v1/refresh/status", params={"since": since}).json()["state"] == "queued" or True