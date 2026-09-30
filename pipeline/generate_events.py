import argparse, hashlib, random, sys, datetime as dt
from collections import defaultdict
import psycopg
from common import DSN, UTC, PLANS, PLAN_MRR, FEATURES
from ingest import ingest_feature_events, ingest_subscription_events, log_run


def profile(org):
    r = random.Random(str(org))
    return {"p_active": r.uniform(0.35, 0.75),
            "max_events": r.randint(3, 10),
            "weights": [r.random() + 0.1 for _ in FEATURES]}


def gen_features(org, users, day, prof, rng, factor):
    rows = []
    p = min(1.0, prof["p_active"] * (0.3 if day.weekday() >= 5 else 1.0) * factor)
    base = dt.datetime.combine(day, dt.time(6), tzinfo=UTC)
    for u in users:
        if rng.random() > p:
            continue
        for _ in range(rng.randint(1, prof["max_events"])):
            feature = rng.choices(FEATURES, weights=prof["weights"])[0]
            ts = base + dt.timedelta(seconds=rng.randint(0, 14 * 3600))
            key = hashlib.sha1(f"{org}|{u}|{feature}|{ts.isoformat()}".encode()).hexdigest()
            rows.append((org, u, feature, ts, key))
    return rows


def step_subscription(org, day, st, rng):
    """Advance one day of billing for an active org. Mutates st, returns event rows."""
    ev = []
    at = lambda h: dt.datetime.combine(day, dt.time(h), tzinfo=UTC)
    if (day - st["last_billed"]).days >= 30:
        ev.append((org, "renewed", st["plan"], PLAN_MRR[st["plan"]], at(9), f"renew-{org}-{day}"))
        st["last_billed"] = day
    roll = rng.random()
    if roll < 0.004 and st["plan"] != "scale":
        st["plan"] = PLANS[PLANS.index(st["plan"]) + 1]
        ev.append((org, "upgraded", st["plan"], PLAN_MRR[st["plan"]], at(10), f"upgrade-{org}-{day}"))
    elif roll < 0.007 and st["plan"] != "starter":
        st["plan"] = PLANS[PLANS.index(st["plan"]) - 1]
        ev.append((org, "downgraded", st["plan"], PLAN_MRR[st["plan"]], at(10), f"downgrade-{org}-{day}"))
    elif roll < 0.010:
        st["status"] = "canceled"
        ev.append((org, "canceled", st["plan"], 0, at(11), f"cancel-{org}-{day}"))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="truncate raw event tables (dev only)")
    ap.add_argument("--yes", action="store_true", help="confirm --reset")
    ap.add_argument("--backfill-days", type=int)
    ap.add_argument("--date", help="regenerate one day, YYYY-MM-DD")
    ap.add_argument("--demo-anomaly", action="store_true",
                    help="make one org go quiet for the last 2 days of the range")
    args = ap.parse_args()

    end = dt.datetime.now(UTC).date() - dt.timedelta(days=1)   # only complete UTC days

    with psycopg.connect(DSN) as conn:
        if args.reset:
            if not args.yes:
                sys.exit("--reset deletes all events. Add --yes to confirm (dev project only).")
            conn.execute("truncate raw.feature_events, raw.subscription_events restart identity")

        has_events = conn.execute("select exists(select 1 from raw.feature_events)").fetchone()[0]
        if args.backfill_days:
            if has_events:
                sys.exit("events already exist. Use --reset --yes first, or drop --backfill-days.")
            start = end - dt.timedelta(days=args.backfill_days - 1)
        elif args.date:
            start = end = dt.date.fromisoformat(args.date)
        else:
            latest = conn.execute(
                "select (max(occurred_at) at time zone 'UTC')::date from raw.feature_events"
            ).fetchone()[0]
            start = (latest + dt.timedelta(days=1)) if latest else end
        if start > end:
            print("already up to date")
            return

        orgs = dict(conn.execute("select id, plan from app.orgs order by id").fetchall())
        members = defaultdict(list)
        for org, uid in conn.execute("select org_id, user_id from app.org_members"):
            members[org].append(uid)

        # billing state per org, loaded from what is already stored
        state = {}
        for org, etype, plan in conn.execute(
                "select distinct on (org_id) org_id, event_type, plan from raw.subscription_events"
                " order by org_id, occurred_at desc, id desc"):
            state[org] = {"plan": plan, "status": "canceled" if etype == "canceled" else "active"}
        for org, last in conn.execute(
                "select org_id, (max(occurred_at) at time zone 'UTC')::date"
                " from raw.subscription_events where event_type in ('started','renewed')"
                " group by org_id"):
            state[org]["last_billed"] = last
        existing_sub_days = {(o, d) for o, d in conn.execute(
            "select org_id, (occurred_at at time zone 'UTC')::date from raw.subscription_events")}

        feats, subs = [], []
        for org, plan in orgs.items():
            if org not in state:                       # brand-new org: open its subscription
                state[org] = {"plan": plan, "status": "active", "last_billed": start}
                subs.append((org, "started", plan, PLAN_MRR[plan],
                             dt.datetime.combine(start, dt.time(9), tzinfo=UTC), f"start-{org}"))
                existing_sub_days.add((org, start))

        quiet_org = sorted(orgs)[0] if args.demo_anomaly else None
        profs = {o: profile(o) for o in orgs}
        day = start
        while day <= end:
            for org in orgs:
                st = state[org]
                if st["status"] == "canceled":
                    continue
                rng = random.Random(f"{org}-{day}")
                factor = 0.05 if (org == quiet_org and day >= end - dt.timedelta(days=1)) else 1.0
                feats += gen_features(org, members[org], day, profs[org], rng, factor)
                if (org, day) not in existing_sub_days:
                    subs += step_subscription(org, day, st, rng)
            day += dt.timedelta(days=1)

        f_ins, f_rej = ingest_feature_events(conn, feats)
        s_ins, s_rej = ingest_subscription_events(conn, subs)
        log_run(conn, "generator:features", len(feats), f_ins, f_rej)
        log_run(conn, "generator:subscriptions", len(subs), s_ins, s_rej)
        conn.commit()
        print(f"{start} -> {end}: features +{f_ins} ({f_rej} rejected), subscriptions +{s_ins}")


if __name__ == "__main__":
    main()