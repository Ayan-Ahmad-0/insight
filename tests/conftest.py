import pytest, psycopg
from helpers import DSN, TENANT_TABLES


@pytest.fixture(scope="session")
def truth():
    """Ground truth read with the privileged role: (org ids, per-table counts by org)."""
    with psycopg.connect(DSN) as conn:
        orgs = [r[0] for r in conn.execute("select id from app.orgs order by name")]
        counts = {
            t: dict(conn.execute(f"select {col}, count(*) from {t} group by 1").fetchall())
            for t, col in TENANT_TABLES.items()
        }
    assert len(orgs) >= 2, "seed the database first"
    return orgs, counts