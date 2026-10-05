"""Onboard one real customer org. Run locally with the OWNER database URL and the service-role key.
Dry run by default. Never run on the API server or in CI."""
import argparse, json, os, secrets, sys, uuid, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PLANS = ("starter", "growth", "scale")


def admin_call(method, path, body=None):
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        os.environ["SUPABASE_URL"].rstrip("/") + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase admin API {e.code}: {e.read().decode()[:300]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--plan", choices=PLANS, default="starter")
    p.add_argument("--mrr-cents", type=int, default=0)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    name, email = a.name.strip(), a.email.strip().lower()
    db = os.environ["DATABASE_URL"]

    with psycopg.connect(db) as conn:
        if conn.execute("select 1 from app.orgs where lower(name) = lower(%s)", [name]).fetchone():
            sys.exit(f"An organisation named '{name}' already exists.")

    print(f"Database:     {urlparse(db).hostname}")
    print(f"Organisation: {name}  (plan {a.plan}, MRR {a.mrr_cents} cents)")
    print(f"First user:   {email} (admin)")
    print("Data source:  customer (the synthetic generator will skip this org)")
    if not a.execute:
        print("\nDry run only. Re-run with --execute to create it.")
        return

    org_id = uuid.uuid4()
    password = secrets.token_urlsafe(12)
    user = admin_call("POST", "/auth/v1/admin/users", {
        "email": email, "password": password, "email_confirm": True,
        "app_metadata": {"org_id": str(org_id)}})
    user_id = user["id"]
    try:
        with psycopg.connect(db) as conn:  # commits on clean exit, rolls back on error
            conn.execute("insert into app.orgs (id, name, plan, data_source) values (%s, %s, %s, 'customer')",
                         [org_id, name, a.plan])
            conn.execute("insert into app.org_members (org_id, user_id, role) values (%s, %s, 'admin')",
                         [org_id, user_id])
            conn.execute("""insert into raw.subscription_events
                            (org_id, event_type, plan, mrr_cents, occurred_at, event_key)
                            values (%s, 'started', %s, %s, now(), %s)""",
                         [org_id, a.plan, a.mrr_cents, f"started-{org_id}"])
    except Exception:
        try:
            admin_call("DELETE", f"/auth/v1/admin/users/{user_id}")  # don't leave an orphan login
        except RuntimeError as e:
            print("WARNING: could not remove the auth user:", e)
        raise

    print(f"\nCreated.\n  org_id:   {org_id}\n  email:    {email}\n  password: {password}")
    print("The password is shown once. Send it over a secure channel.")


if __name__ == "__main__":
    main()