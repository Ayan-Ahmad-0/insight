import os, sys, pathlib
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from dbt.cli.main import dbtRunner

load_dotenv()
u = urlparse(os.environ["DATABASE_URL"])
os.environ.update(
    DBT_HOST=u.hostname,
    DBT_PORT=str(u.port or 5432),
    DBT_USER=unquote(u.username),
    DBT_PASSWORD=unquote(u.password),
    DBT_DBNAME=(u.path or "/postgres").lstrip("/"),
)
proj = str(pathlib.Path(__file__).parent / "dbt_project")
res = dbtRunner().invoke(sys.argv[1:] + ["--project-dir", proj, "--profiles-dir", proj])
sys.exit(0 if res.success else 1)