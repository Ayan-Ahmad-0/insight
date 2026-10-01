create schema if not exists ai;

create table ai.definitions (
  id text primary key,
  title text not null,
  body text not null
);

create table ai.org_settings (
  org_id uuid primary key references app.orgs(id) on delete cascade,
  ai_enabled boolean not null default true,
  daily_budget_usd numeric(10,4) not null default 0.50
);

create table ai.calls (
  id bigint generated always as identity primary key,
  org_id uuid not null references app.orgs(id) on delete cascade,
  user_id uuid,
  request_id text not null,
  question text not null,
  answer text,
  status text not null check (status in
    ('ok','refused','blocked_disabled','blocked_budget','error')),
  model text,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  cost_usd numeric(12,6) not null default 0,
  latency_ms int,
  tool_trace jsonb not null default '[]',
  created_at timestamptz not null default now()
);
create index on ai.calls (org_id, created_at);

alter table ai.definitions enable row level security;
alter table ai.org_settings enable row level security;
alter table ai.calls enable row level security;

create policy defs_read on ai.definitions for select using (true);
create policy settings_read on ai.org_settings for select using (org_id = app.current_org());
create policy calls_read on ai.calls for select using (org_id = app.current_org());
create policy calls_insert on ai.calls for insert with check (org_id = app.current_org());

grant usage on schema ai to authenticated;
grant select on ai.definitions, ai.org_settings, ai.calls to authenticated;
grant insert on ai.calls to authenticated;
-- org_settings: no insert/update grant. Only the operator changes the kill switch or budget.

insert into ai.definitions (id, title, body) values
('active_users','Active users','Distinct users with at least one feature event on a given UTC day.'),
('events','Events','Total feature events recorded for the organisation on a given UTC day.'),
('feature_usage','Feature usage','Number of events per feature over a chosen date range, highest first.'),
('mrr','MRR','Monthly recurring revenue per day, derived from subscription events (started, upgraded, downgraded, renewed, canceled). Reported in dollars.'),
('churn','Churn / cancellation','A cancellation is a canceled subscription event. After it, status shows canceled and MRR drops.'),
('morning_digest','Morning digest','Compares the latest complete day with the same weekday in recent weeks. Flags usage drop, usage spike and canceled.'),
('data_freshness','Data freshness','The pipeline runs daily at 03:00 UTC. Events posted through the API appear after the next run. Yesterday is the latest complete UTC day.'),
('date_ranges','Date ranges','Default range is the last 30 complete UTC days. The maximum range is 366 days.'),
('plans','Plans','Plans are starter, growth and scale.')
on conflict (id) do nothing;