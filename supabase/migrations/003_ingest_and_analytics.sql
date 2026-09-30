create schema if not exists analytics;   -- tenant-facing marts
create schema if not exists staging;     -- internal views, never granted to tenants
grant usage on schema analytics to authenticated;

-- Operational log of every ingest run. Tenants get no grant and no policy.
create table raw.ingest_runs (
  id            bigint generated always as identity primary key,
  source        text not null,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  rows_received int not null default 0,
  rows_inserted int not null default 0,
  rows_rejected int not null default 0,
  status        text not null default 'ok',
  error         text
);
alter table raw.ingest_runs enable row level security;

-- Tenants may send their own feature events (used by POST /events on Day 3).
-- Subscription events come from billing, so tenants get no insert path there.
create policy tenant_insert on raw.feature_events
  for insert with check (org_id = app.current_org());
grant insert on raw.feature_events to authenticated;