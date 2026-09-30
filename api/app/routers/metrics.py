import datetime as dt
from fastapi import APIRouter, Depends, Query
from ..auth import Caller, get_caller
from ..db import tenant_conn
from ..errors import ApiError
from ..schemas import Digest, FeatureUsage, MrrDay, UsageDay

router = APIRouter(prefix="/v1", tags=["metrics"])

DIGEST_COLS = """digest_date, events::bigint as events, active_users, weekly_active_users,
    avg_active_same_weekday, top_feature, plan, status, mrr_cents, mrr_change_7d_cents,
    flag_usage_drop, flag_usage_spike, flag_canceled"""


def date_range(from_: dt.date | None = Query(None, alias="from"),
               to: dt.date | None = Query(None)):
    to = to or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    from_ = from_ or (to - dt.timedelta(days=29))
    if from_ > to:
        raise ApiError(422, "bad_range", "'from' must not be after 'to'.")
    if (to - from_).days > 365:
        raise ApiError(422, "range_too_large", "Range is limited to 366 days.")
    return from_, to


@router.get("/usage/daily", response_model=list[UsageDay])
def usage_daily(caller: Caller = Depends(get_caller), rng=Depends(date_range)):
    with tenant_conn(caller) as conn:
        return conn.execute(
            """select usage_date, events::bigint as events, active_users, weekly_active_users
               from analytics.daily_org_activity
               where usage_date between %s and %s order by usage_date""", rng).fetchall()


@router.get("/usage/features", response_model=list[FeatureUsage])
def usage_features(caller: Caller = Depends(get_caller), rng=Depends(date_range)):
    with tenant_conn(caller) as conn:
        return conn.execute(
            """select feature, sum(event_count)::bigint as events
               from analytics.daily_feature_usage
               where usage_date between %s and %s
               group by feature order by events desc, feature""", rng).fetchall()


@router.get("/revenue/mrr", response_model=list[MrrDay])
def revenue_mrr(caller: Caller = Depends(get_caller), rng=Depends(date_range)):
    with tenant_conn(caller) as conn:
        return conn.execute(
            """select mrr_date, plan, mrr_cents, status
               from analytics.mrr_daily
               where mrr_date between %s and %s order by mrr_date""", rng).fetchall()


@router.get("/digest", response_model=Digest)
def digest(caller: Caller = Depends(get_caller), date: dt.date | None = None):
    with tenant_conn(caller) as conn:
        if date:
            row = conn.execute(
                f"select {DIGEST_COLS} from analytics.morning_digest where digest_date = %s",
                [date]).fetchone()
        else:
            row = conn.execute(
                f"select {DIGEST_COLS} from analytics.morning_digest "
                "order by digest_date desc limit 1").fetchone()
    if row is None:
        raise ApiError(404, "no_digest", "No digest available for that date.")
    return row