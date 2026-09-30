import psycopg
from helpers import DSN


def test_every_table_has_rls_enabled():
    with psycopg.connect(DSN) as conn:
        rows = conn.execute("""
            select n.nspname, c.relname
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname in ('app', 'raw', 'analytics', 'ai')
              and c.relkind in ('r', 'p')
              and not c.relrowsecurity
        """).fetchall()
    assert rows == [], f"tables without RLS: {rows}"