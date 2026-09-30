select 'daily_org_activity' as model, org_id, usage_date as day
from {{ ref('daily_org_activity') }} group by 1, 2, 3 having count(*) > 1
union all
select 'mrr_daily', org_id, mrr_date
from {{ ref('mrr_daily') }} group by 1, 2, 3 having count(*) > 1
union all
select 'morning_digest', org_id, digest_date
from {{ ref('morning_digest') }} group by 1, 2, 3 having count(*) > 1