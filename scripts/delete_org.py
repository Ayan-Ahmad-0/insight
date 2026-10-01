"""Delete an organisation completely and write a receipt.

Dry run:  python scripts/delete_org.py --org-id <uuid>
Execute:  python scripts/delete_org.py --org-id <uuid> --execute --confirm-name "<exact org name>"

Needs DATABASE_URL (owner role, bypasses RLS), SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
Run from your own machine only. The service-role key never goes on the API host."""
import argparse
import getpass
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()
RECEIPTS = Path(__file__).resolve().parent.parent / "receipts"

NOT_COVERED = [
    "Hosting request logs (Render) may contain the org id until their retention window ends.",
    "Database backups / point-in-time recovery keep a copy until they expire.",
    "A JWT issued before deletion stays valid until it expires (about 1 hour) but now matches no data.",
]


class DeleteError(Exception):
    pass


def org_tables(conn):
    rows = conn.execute("""
        select c.table_schema, c.table_name
        from information_schema.columns c
        join information_schema.tables t
          on t.table_schema = c.table_schema and t.table_name = c.table_name
        where c.column_name = 'org_id' and t.table_type = 'BASE TABLE'
          and c.table_schema not in ('pg_catalog', 'information_schema')
        order by 1, 2""").fetchall()
    return [(s, t) for s, t in rows]


def inventory(conn, org_id):
    inv = {}
    for s, t in org_tables(conn):
        q = sql.SQL("select count(*) from {}.{} where org_id = %s").format(
            sql.Identifier(s), sql.Identifier(t))
        inv[f"{s}.{t}"] = conn.execute(q, [org_id]).fetchone()[0]
    inv["app.orgs"] = conn.execute(
        "select count(*) from app.orgs where id = %s", [org_id]).fetchone()[0]
    return inv


def admin_delete_user(user_id):
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users/{user_id}", method="DELETE",
        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        urllib.request.urlopen(req, timeout=30)
        return "deleted"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "already_gone"
        raise


def delete_org(org_id, execute=False, confirm_name=None, operator=None):
    url = os.environ["DATABASE_URL"]
    host = url.split("@")[-1].split("/")[0]
    conn = psycopg.connect(url)
    try:
        bypass = conn.execute(
            "select rolbypassrls or rolsuper from pg_roles where rolname = current_user").fetchone()[0]
        if not bypass:
            raise DeleteError("this DB role is subject to RLS, so counts would be wrong; use the owner role")

        org = conn.execute("select id, name from app.orgs where id = %s", [org_id]).fetchone()
        if not org:
            raise DeleteError("organisation not found")
        name = org[1]
        user_ids = [r[0] for r in conn.execute(
            "select user_id from app.org_members where org_id = %s", [org_id]).fetchall()]
        before = inventory(conn, org_id)

        if not execute:
            return {"dry_run": True, "org_id": str(org_id), "org_name": name,
                    "database_host": host, "auth_users": len(user_ids), "rows_before": before}
        if confirm_name != name:
            raise DeleteError("--confirm-name does not match the organisation name")

        with conn.transaction():
            for s, t in org_tables(conn):
                if s == "analytics":      # dbt tables have no foreign key, so delete explicitly
                    conn.execute(sql.SQL("delete from {}.{} where org_id = %s").format(
                        sql.Identifier(s), sql.Identifier(t)), [org_id])
            conn.execute("delete from app.orgs where id = %s", [org_id])   # cascades the rest
            after = inventory(conn, org_id)
            leftovers = {k: v for k, v in after.items() if v}
            if leftovers:
                raise DeleteError(f"rows remain, rolled back: {leftovers}")
        conn.commit()

        auth = {}
        for uid in user_ids:
            if conn.execute("select 1 from app.org_members where user_id = %s limit 1",
                            [uid]).fetchone():
                auth[str(uid)] = "kept (member of another org)"
            else:
                auth[str(uid)] = admin_delete_user(uid)
        remaining = conn.execute(
            "select count(*) from auth.users where id = any(%s)", [user_ids]).fetchone()[0]
        kept = sum(1 for v in auth.values() if v.startswith("kept"))
        complete = remaining == kept

        receipt = {
            "receipt_version": 1, "org_id": str(org_id), "org_name": name,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "operator": operator or getpass.getuser(), "database_host": host,
            "tables_scanned": sorted(before), "rows_before": before, "rows_after": after,
            "auth_users": auth, "auth_users_remaining": remaining,
            "status": "complete" if complete else "partial", "not_covered": NOT_COVERED}
        body = json.dumps(receipt, indent=2, sort_keys=True)
        receipt["sha256"] = hashlib.sha256(body.encode()).hexdigest()
        RECEIPTS.mkdir(exist_ok=True)
        path = RECEIPTS / f"{org_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        receipt["receipt_path"] = str(path)
        return receipt
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--org-id", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm-name")
    a = ap.parse_args()
    try:
        out = delete_org(a.org_id, a.execute, a.confirm_name)
    except DeleteError as e:
        raise SystemExit(f"REFUSED: {e}")
    print(json.dumps(out, indent=2, default=str))