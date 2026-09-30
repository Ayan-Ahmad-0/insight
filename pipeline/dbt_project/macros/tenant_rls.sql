{% macro tenant_rls(column='org_id') %}
  alter table {{ this }} enable row level security;
  drop policy if exists tenant_isolation on {{ this }};
  create policy tenant_isolation on {{ this }}
    for select using ({{ column }} = app.current_org());
  grant select on {{ this }} to authenticated;
{% endmacro %}