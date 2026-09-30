import os, pathlib, psycopg
from dotenv import load_dotenv

load_dotenv()
MIG = pathlib.Path(__file__).resolve().parent.parent / "supabase" / "migrations"

with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
    conn.execute("create schema if not exists app")
    conn.execute("""create table if not exists app.schema_migrations (
        name text primary key, applied_at timestamptz default now())""")
    conn.execute("alter table app.schema_migrations enable row level security")
    done = {r[0] for r in conn.execute("select name from app.schema_migrations")}
    for f in sorted(MIG.glob("*.sql")):
        if f.name in done:
            continue
        print("applying", f.name)
        with conn.transaction():
            conn.execute(f.read_text())
            conn.execute("insert into app.schema_migrations(name) values (%s)", [f.name])
print("migrations up to date")