from fastapi import APIRouter, Depends
from ..auth import Caller, get_caller
from ..db import pool, tenant_conn
from ..errors import ApiError
from ..schemas import AskIn, Me

router = APIRouter()


@router.get("/health", tags=["meta"])
def health():
    try:
        with pool.connection() as conn:
            conn.execute("select 1")
    except Exception:
        raise ApiError(503, "db_unavailable", "Database is not reachable.")
    return {"status": "ok"}


@router.get("/v1/me", response_model=Me, tags=["meta"])
def me(caller: Caller = Depends(get_caller)):
    with tenant_conn(caller) as conn:
        org = conn.execute("select id, name, plan from app.orgs").fetchone()
        member = conn.execute(
            "select role from app.org_members where user_id = %s", [caller.user_id]).fetchone()
    if org is None:
        raise ApiError(404, "org_not_found", "Organisation not found.")
    return {"org_id": org["id"], "org_name": org["name"], "plan": org["plan"],
            "user_id": caller.user_id, "role": member["role"] if member else None}


@router.post("/v1/ask", tags=["analyst"])
def ask(body: AskIn, caller: Caller = Depends(get_caller)):
    raise ApiError(501, "not_implemented", "The analyst arrives on Day 4.")