import os, sys, httpx
from dotenv import load_dotenv

load_dotenv()
r = httpx.post(
    f"{os.environ['SUPABASE_URL']}/auth/v1/token?grant_type=password",
    headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
    json={"email": sys.argv[1], "password": os.environ["SEED_PASSWORD"]},
    timeout=20,
)
r.raise_for_status()
print(r.json()["access_token"])