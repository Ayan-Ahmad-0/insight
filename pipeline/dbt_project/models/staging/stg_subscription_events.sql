select id as event_id, org_id, event_type, plan, mrr_cents, occurred_at
from {{ source('raw', 'subscription_events') }}