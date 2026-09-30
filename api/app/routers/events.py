from fastapi import APIRouter, Depends
from ..auth import Caller, get_caller
from ..db import tenant_conn
from ..schemas import EventBatch, IngestResult

router = APIRouter(prefix="/v1", tags=["events"])

SQL = """insert into raw.feature_events(org_id, user_id, feature, occurred_at, event_key)
         values (%s, %s, %s, %s, %s)
         on conflict (org_id, event_key) do nothing"""


@router.post("/events", response_model=IngestResult)
def ingest(batch: EventBatch, caller: Caller = Depends(get_caller)):
    # org_id comes from the token. The insert policy from migration 003 rejects anything else.
    rows = [(caller.org_id, e.user_id, e.feature, e.occurred_at, e.event_key)
            for e in batch.events]
    with tenant_conn(caller) as conn:
        with conn.cursor() as cur:
            cur.executemany(SQL, rows)
            inserted = max(cur.rowcount, 0)
    return {"received": len(rows), "inserted": inserted, "duplicates": len(rows) - inserted}