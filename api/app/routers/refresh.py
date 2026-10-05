"""On-demand dashboard update.

The API never holds database owner credentials, so it cannot run dbt itself. Instead an org admin asks
for a rebuild, and the API starts the 'refresh-marts' GitHub Actions workflow, which holds the owner
credentials as a secret. The page then polls the status until the run finishes.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Query

from ..auth import Caller, get_caller
from ..config import settings
from ..db import tenant_conn
from ..errors import ApiError

log = logging.getLogger("insight")
router = APIRouter(prefix="/v1", tags=["refresh"])

GITHUB = "https://api.github.com"
_last_request: dict[str, float] = {}          # org id -> monotonic time of its last accepted request
_cache: dict = {"at": 0.0, "runs": []}        # short cache so polling pages don't hammer GitHub


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.refresh_github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _workflow_url(suffix: str) -> str:
    return f"{GITHUB}/repos/{settings.refresh_repo}/actions/workflows/{settings.refresh_workflow}/{suffix}"


def _is_admin(caller: Caller) -> bool:
    with tenant_conn(caller) as conn:
        row = conn.execute("select role from app.org_members where user_id = %s",
                           [caller.user_id]).fetchone()
    return bool(row) and row["role"] == "admin"


def _dispatch(org_id: str) -> None:
    try:
        r = httpx.post(_workflow_url("dispatches"), headers=_headers(), timeout=10,
                       json={"ref": settings.refresh_ref, "inputs": {"requested_by": org_id}})
    except httpx.HTTPError:
        log.exception("refresh dispatch failed")
        raise ApiError(502, "refresh_failed", "Could not start the update. Please try again later.")
    if r.status_code != 204:
        log.warning("refresh dispatch rejected by GitHub: %s", r.status_code)
        raise ApiError(502, "refresh_failed", "Could not start the update. Please try again later.")


def _runs() -> list[dict]:
    try:
        r = httpx.get(_workflow_url("runs"), headers=_headers(), timeout=10,
                      params={"event": "workflow_dispatch", "per_page": 10})
    except httpx.HTTPError:
        log.exception("refresh status failed")
        raise ApiError(502, "refresh_status_unavailable", "Could not check the update. Please try again.")
    if r.status_code != 200:
        log.warning("refresh status rejected by GitHub: %s", r.status_code)
        raise ApiError(502, "refresh_status_unavailable", "Could not check the update. Please try again.")
    return r.json().get("workflow_runs", [])


def _runs_cached() -> list[dict]:
    if time.monotonic() - _cache["at"] > 3:
        _cache["runs"], _cache["at"] = _runs(), time.monotonic()
    return _cache["runs"]


def _require_enabled() -> None:
    if not settings.refresh_github_token:
        raise ApiError(503, "refresh_unavailable", "Updating on demand is not enabled.")


@router.post("/refresh", status_code=202)
def request_refresh(caller: Caller = Depends(get_caller)):
    _require_enabled()
    if not _is_admin(caller):
        raise ApiError(403, "forbidden", "Only organisation admins can update the dashboard.")
    key, now = str(caller.org_id), time.monotonic()
    last = _last_request.get(key)
    if last is not None and now - last < settings.refresh_cooldown_s:
        raise ApiError(429, "too_soon", "An update was just requested. Wait a minute and try again.")
    _dispatch(key)
    _last_request[key] = now          # only after GitHub accepted it, so a failure doesn't lock the org out
    return {"requested_at": datetime.now(timezone.utc).isoformat(), "state": "queued"}


@router.get("/refresh/status")
def refresh_status(since: datetime = Query(..., description="requested_at from POST /v1/refresh"),
                   caller: Caller = Depends(get_caller)):
    _require_enabled()
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    cutoff = since - timedelta(seconds=5)          # small allowance for clock differences
    for run in _runs_cached():                     # GitHub lists newest first
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        if created < cutoff:
            continue
        if run["status"] == "completed":
            return {"state": "succeeded" if run.get("conclusion") == "success" else "failed"}
        return {"state": "running" if run["status"] == "in_progress" else "queued"}
    return {"state": "queued"}                     # GitHub hasn't listed our run yet