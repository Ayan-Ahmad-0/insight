do $$
begin
  if not exists (select from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
end $$;

create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique
);
alter table auth.users enable row level security;   -- Supabase has this on too
create schema if not exists extensions;