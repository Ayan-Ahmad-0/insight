import json
from contextlib import contextmanager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from .config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=settings.db_pool_max,
    kwargs={"row_factory": dict_row},
    check=ConnectionPool.check_connection,
    open=False,
    timeout=10,
)


@contextmanager
def tenant_conn(caller):
    """A transaction that runs as the tenant. RLS decides which rows exist."""
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("select set_config('request.jwt.claims', %s, true)",
                         [json.dumps(caller.claims)])
            conn.execute("set local role authenticated")
            conn.execute("set local statement_timeout = '5s'")
            yield conn