select id as event_id, org_id, user_id, feature, occurred_at
from {{ source('raw', 'feature_events') }}