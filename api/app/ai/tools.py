from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from psycopg.rows import dict_row

from app.db import tenant_conn

MAX_ROWS = 60


def _clean(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _rows(caller, sql, params=None):
    with tenant_conn(caller) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchmany(MAX_ROWS)
    return [{k: _clean(v) for k, v in r.items()} for r in rows]


def _range(args):
    today = datetime.now(timezone.utc).date()
    try:
        end = date.fromisoformat(args.get("to_date") or str(today - timedelta(days=1)))
        start = date.fromisoformat(args.get("from_date") or str(end - timedelta(days=29)))
    except ValueError:
        raise ValueError("dates must be YYYY-MM-DD")
    if start > end:
        raise ValueError("from_date is after to_date")
    if (end - start).days > 365:
        raise ValueError("range too long, max 366 days")
    return start, end


# NOTE: no "where org_id" anywhere. RLS is the single source of truth.
# Copy the SQL/column names from your existing routers/metrics.py if they differ.

def get_usage_daily(caller, args):
    s, e = _range(args)
    return {"from": str(s), "to": str(e), "rows": _rows(caller,
        "select date, events, active_users from analytics.daily_org_activity "
        "where date between %s and %s order by date", [s, e])}


def get_feature_usage(caller, args):
    s, e = _range(args)
    return {"from": str(s), "to": str(e), "rows": _rows(caller,
        "select feature, sum(events) as events from analytics.daily_feature_usage "
        "where date between %s and %s group by feature order by events desc limit 20", [s, e])}


def get_mrr(caller, args):
    s, e = _range(args)
    return {"from": str(s), "to": str(e), "rows": _rows(caller,
        "select date, mrr_cents / 100.0 as mrr_usd, status from analytics.mrr_daily "
        "where date between %s and %s order by date", [s, e])}


def get_digest(caller, args):
    return {"rows": _rows(caller,
        "select * from analytics.morning_digest order by date desc limit 1")}


def get_definitions(caller, args):
    term = (args.get("term") or "").strip().lower()[:100]
    rows = _rows(caller, "select id, title, body from ai.definitions order by id")
    hits = [r for r in rows
            if term and any(w in f"{r['title']} {r['body']}".lower() for w in term.split())]
    return {"definitions": hits or rows}


_DATES = {
    "from_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
    "to_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
}

DECLARATIONS = [
    {"name": "get_usage_daily",
     "description": "Daily total events and active users for this organisation.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_feature_usage",
     "description": "Event counts per feature for this organisation over a date range.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_mrr",
     "description": "Daily MRR (USD) and subscription status for this organisation.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_digest",
     "description": "The latest morning digest for this organisation, including flags.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_definitions",
     "description": "Definitions of metrics and terms. Pass the term being asked about.",
     "parameters": {"type": "object",
                    "properties": {"term": {"type": "string"}}}},
]

_DISPATCH = {
    "get_usage_daily": get_usage_daily,
    "get_feature_usage": get_feature_usage,
    "get_mrr": get_mrr,
    "get_digest": get_digest,
    "get_definitions": get_definitions,
}


def run_tool(caller, name, args):
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ValueError("unknown tool")
    return fn(caller, args)