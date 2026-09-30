create schema if not exists app;
create schema if not exists raw;

create table app.orgs (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  plan       text not null default 'starter'
             check (plan in ('starter','growth','scale')),
  created_at timestamptz not null default now()
);

create table app.org_members (
  org_id  uuid not null references app.orgs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role    text not null default 'member' check (role in ('admin','member')),
  primary key (org_id, user_id)
);
create index on app.org_members (user_id);

create table raw.feature_events (
  id          bigint generated always as identity primary key,
  org_id      uuid not null references app.orgs(id) on delete cascade,
  user_id     uuid,
  feature     text not null,
  occurred_at timestamptz not null,
  event_key   text not null,
  properties  jsonb not null default '{}',
  unique (org_id, event_key)
);
create index on raw.feature_events (org_id, occurred_at);

create table raw.subscription_events (
  id          bigint generated always as identity primary key,
  org_id      uuid not null references app.orgs(id) on delete cascade,
  event_type  text not null
              check (event_type in ('started','upgraded','downgraded','renewed','canceled')),
  plan        text not null,
  mrr_cents   integer not null,
  occurred_at timestamptz not null,
  event_key   text not null,
  unique (org_id, event_key)
);
create index on raw.subscription_events (org_id, occurred_at);