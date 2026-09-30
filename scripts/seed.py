import os, sys, random, uuid, datetime as dt
import psycopg
from dotenv import load_dotenv
from faker import Faker
from supabase import create_client

load_dotenv()
random.seed(42)
Faker.seed(42)
fake = Faker()

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
PASSWORD = os.environ["SEED_PASSWORD"]

FEATURES = ["dashboard", "reports", "export_csv", "api_keys",
            "integrations", "alerts", "team_invite", "billing"]
PLAN_MRR = {"starter": 4900, "growth": 19900, "scale": 59900}


def slug(s):
    return "".join(c for c in s.lower() if c.isalnum())[:20] or "org"


sizes = ([random.randint(25, 40) for _ in range(3)]
         + [random.randint(8, 15) for _ in range(12)]
         + [random.randint(3, 7) for _ in range(25)])
random.shuffle(sizes)

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    if conn.execute("select count(*) from app.orgs").fetchone()[0]:
        sys.exit("orgs already exist. Run scripts/reset_dev.py first.")

    now = dt.datetime.now(dt.timezone.utc)
    for i, size in enumerate(sizes):
        name = fake.unique.company()
        plan = random.choice(list(PLAN_MRR))
        org_id = conn.execute(
            "insert into app.orgs(name, plan) values (%s, %s) returning id",
            [name, plan]).fetchone()[0]

        user_ids = []
        for u in range(size):
            res = sb.auth.admin.create_user({
                "email": f"user{u+1}@{slug(name)}{i}.example.test",
                "password": PASSWORD,
                "email_confirm": True,
                "app_metadata": {"org_id": str(org_id)},   # server-controlled claim
            })
            uid = res.user.id
            conn.execute(
                "insert into app.org_members(org_id, user_id, role) values (%s, %s, %s)",
                [org_id, uid, "admin" if u == 0 else "member"])
            user_ids.append(uid)

        events = [(org_id, random.choice(user_ids), random.choice(FEATURES),
                   now - dt.timedelta(minutes=random.randint(0, 30 * 24 * 60)),
                   str(uuid.uuid4()))
                  for _ in range(size * 30)]
        with conn.cursor() as cur:
            cur.executemany(
                "insert into raw.feature_events(org_id, user_id, feature, occurred_at, event_key)"
                " values (%s, %s, %s, %s, %s)", events)

        conn.execute(
            "insert into raw.subscription_events"
            "(org_id, event_type, plan, mrr_cents, occurred_at, event_key)"
            " values (%s, 'started', %s, %s, %s, %s)",
            [org_id, plan, PLAN_MRR[plan], now - dt.timedelta(days=60), f"seed-start-{org_id}"])

        conn.commit()
        print(f"[{i+1}/40] {name}: {size} users, {len(events)} events")