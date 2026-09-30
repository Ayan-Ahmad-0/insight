import os, psycopg
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

while True:
    users = sb.auth.admin.list_users(page=1, per_page=100)
    if not users:
        break
    for u in users:
        sb.auth.admin.delete_user(u.id)

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute("delete from app.orgs")   # cascades to members and events
print("dev data reset")