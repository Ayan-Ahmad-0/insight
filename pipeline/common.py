import os, datetime as dt
from dotenv import load_dotenv

load_dotenv()
DSN = os.environ["DATABASE_URL"]
UTC = dt.timezone.utc

PLANS = ["starter", "growth", "scale"]
PLAN_MRR = {"starter": 4900, "growth": 19900, "scale": 59900}
FEATURES = ["dashboard", "reports", "export_csv", "api_keys",
            "integrations", "alerts", "team_invite", "billing"]