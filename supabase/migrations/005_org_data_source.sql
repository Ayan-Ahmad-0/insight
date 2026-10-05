alter table app.orgs
  add column if not exists data_source text not null default 'synthetic'
  check (data_source in ('synthetic', 'customer'));