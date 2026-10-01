from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from psycopg.rows import dict_row

from app.db import tenant_conn

MAX_ROWS = 60

DIGEST_COLS = """digest_date, events::bigint as events, active_users, weekly_active_users,
    avg_active_same_weekday, top_feature, plan, status, mrr_cents, mrr_change_7d_cents,
    flag_usage_drop, flag_usage_spike, flag_canceled"""


def _clean(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _rows(caller, sql, params=None):
    """Returns (rows, truncated). Runs under RLS via tenant_conn."""
    with tenant_conn(caller) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchmany(MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    rows = [{k: _clean(v) for k, v in r.items()} for r in rows[:MAX_ROWS]]
    return rows, truncated


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be YYYY-MM-DD")


def _range(args):
    today = datetime.now(timezone.utc).date()
    end = _parse_date(args.get("to_date") or str(today - timedelta(days=1)), "to_date")
    start = _parse_date(args.get("from_date") or str(end - timedelta(days=29)), "from_date")
    if start > end:
        raise ValueError("from_date is after to_date")
    if (end - start).days > 365:
        raise ValueError("range too long, max 366 days")
    return start, end


# NOTE: no "where org_id" anywhere. RLS is the single source of truth.

def get_usage_daily(caller, args):
    s, e = _range(args)
    rows, trunc = _rows(caller,
        """select usage_date, events::bigint as events, active_users, weekly_active_users
           from analytics.daily_org_activity
           where usage_date between %s and %s order by usage_date""", [s, e])
    return {"from": str(s), "to": str(e), "truncated": trunc, "rows": rows,
            "total_events": None if trunc else sum(r["events"] for r in rows),
            "days": len(rows)}


def get_feature_usage(caller, args):
    s, e = _range(args)
    rows, trunc = _rows(caller,
        """select feature, sum(event_count)::bigint as events
           from analytics.daily_feature_usage
           where usage_date between %s and %s
           group by feature order by events desc, feature""", [s, e])
    return {"from": str(s), "to": str(e), "truncated": trunc, "rows": rows,
            "feature_count": len(rows),
            "total_events": None if trunc else sum(r["events"] for r in rows)}


def get_mrr(caller, args):
    s, e = _range(args)
    rows, trunc = _rows(caller,
        """select mrr_date, plan, mrr_cents / 100.0 as mrr_usd, status
           from analytics.mrr_daily
           where mrr_date between %s and %s order by mrr_date""", [s, e])
    return {"from": str(s), "to": str(e), "truncated": trunc, "rows": rows}


def get_digest(caller, args):
    rows, note = [], None
    if args.get("date"):
        d = _parse_date(args["date"], "date")
        rows, _ = _rows(caller,
            f"select {DIGEST_COLS} from analytics.morning_digest where digest_date = %s", [d])
        if not rows:
            note = f"no digest for {d}; showing the latest available instead"
    if not rows:
        rows, _ = _rows(caller,
            f"select {DIGEST_COLS} from analytics.morning_digest "
            "order by digest_date desc limit 1")
    if not rows:
        raise ValueError("no digest available")
    return {"digest": rows[0], "note": note}


def get_definitions(caller, args):
    term = (args.get("term") or "").strip().lower()[:100]
    rows, _ = _rows(caller, "select id, title, body from ai.definitions order by id")
    words = [w for w in term.split() if len(w) > 3]
    hits = [r for r in rows if any(w in f"{r['id']} {r['title']} {r['body']}".lower() for w in words)]
    return {"definitions": hits or rows}


_DATES = {
    "from_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
    "to_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
}

DECLARATIONS = [
    {"name": "get_usage_daily",
     "description": "Daily total events, active users and weekly active users for this organisation.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_feature_usage",
     "description": "Event counts per feature for this organisation over a date range, highest first.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_mrr",
     "description": "Daily MRR (USD), plan and subscription status for this organisation.",
     "parameters": {"type": "object", "properties": _DATES}},
    {"name": "get_digest",
     "description": ("The morning digest for this organisation: events, active users, top feature, "
                     "plan, status, MRR and flags for usage drop, spike and cancellation. "
                     "Defaults to the latest day."),
     "parameters": {"type": "object",
                    "properties": {"date": {"type": "string",
                                            "description": "YYYY-MM-DD, optional"}}}},
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