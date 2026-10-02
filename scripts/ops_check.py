"""Ops check: stale marts, AI error rate (24h), AI spend (24h). Exit 1 on problems."""
import os, sys
from pathlib import Pathgi

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AI_TABLE = "ai.calls"
COL_TIME, COL_STATUS, COL_COST = "created_at", "status", "cost_usd"

ERR_RATE_MAX = float(os.environ.get("AI_ERROR_RATE_MAX", "0.20"))
ERR_MIN_CALLS = int(os.environ.get("AI_ERROR_MIN_CALLS", "5"))
SPEND_24H_MAX = float(os.environ.get("AI_SPEND_24H_MAX", "1.00"))


def main() -> int:
    problems = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        yesterday = conn.execute("select (now() at time zone 'utc')::date - 1").fetchone()[0]

        for table, col in [
            ("analytics.morning_digest", "digest_date"),
            ("analytics.daily_org_activity", "usage_date"),
            ("analytics.mrr_daily", "mrr_date"),
        ]:
            newest = conn.execute(f"select max({col}) from {table}").fetchone()[0]
            if newest is None or newest < yesterday:
                problems.append(f"{table} stale: newest {newest}, expected {yesterday}")

        schema, table = AI_TABLE.split(".")
        have = {r[0] for r in conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema=%s and table_name=%s", [schema, table])}
        missing = {COL_TIME, COL_STATUS, COL_COST} - have
        if missing:
            print(f"Column(s) {sorted(missing)} not in {AI_TABLE}. Actual columns: {sorted(have)}")
            return 2

        total, errors, spend = conn.execute(
            f"""select count(*) filter (where {COL_STATUS} in ('ok','error')),
                       count(*) filter (where {COL_STATUS} = 'error'),
                       coalesce(sum({COL_COST}), 0)
                from {AI_TABLE} where {COL_TIME} > now() - interval '24 hours'"""
        ).fetchone()
        if total >= ERR_MIN_CALLS and errors / total > ERR_RATE_MAX:
            problems.append(f"AI error rate {errors}/{total} ({errors/total:.0%}) in last 24h")
        if float(spend) > SPEND_24H_MAX:
            problems.append(f"AI spend ${float(spend):.4f} in last 24h (limit ${SPEND_24H_MAX})")

    if problems:
        print("Insight ops check FAILED:\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    print("ops check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())