-- The org comes ONLY from app_metadata (server-controlled), never user_metadata.
create or replace function app.current_org() returns uuid
language sql stable as $$
  select nullif(
    current_setting('request.jwt.claims', true)::jsonb
      -> 'app_metadata' ->> 'org_id', ''
  )::uuid
$$;

alter table app.orgs                enable row level security;
alter table app.org_members         enable row level security;
alter table raw.feature_events      enable row level security;
alter table raw.subscription_events enable row level security;

create policy tenant_isolation on app.orgs
  for select using (id = app.current_org());
create policy tenant_isolation on app.org_members
  for select using (org_id = app.current_org());
create policy tenant_isolation on raw.feature_events
  for select using (org_id = app.current_org());
create policy tenant_isolation on raw.subscription_events
  for select using (org_id = app.current_org());

-- Read-only for now. Insert policies arrive on Day 2 with ingestion.
grant usage on schema app, raw to authenticated;
grant select on app.orgs, app.org_members,
                raw.feature_events, raw.subscription_events to authenticated;