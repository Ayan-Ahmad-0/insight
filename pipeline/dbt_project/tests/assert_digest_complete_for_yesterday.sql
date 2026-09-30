select o.id as org_id
from {{ source('app', 'orgs') }} o
left join {{ ref('morning_digest') }} d
  on d.org_id = o.id
 and d.digest_date = (now() at time zone 'UTC')::date - 1
where d.org_id is null
  and exists (select 1 from {{ source('raw', 'feature_events') }} e where e.org_id = o.id)