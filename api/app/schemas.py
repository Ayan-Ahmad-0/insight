import datetime as dt
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Me(BaseModel):
    org_id: UUID
    org_name: str
    plan: str
    user_id: UUID
    role: str | None


class UsageDay(BaseModel):
    usage_date: dt.date
    events: int
    active_users: int
    weekly_active_users: int


class FeatureUsage(BaseModel):
    feature: str
    events: int


class MrrDay(BaseModel):
    mrr_date: dt.date
    plan: str | None
    mrr_cents: int
    status: str


class Digest(BaseModel):
    digest_date: dt.date
    events: int
    active_users: int
    weekly_active_users: int
    avg_active_same_weekday: float | None
    top_feature: str | None
    plan: str | None
    status: str | None
    mrr_cents: int | None
    mrr_change_7d_cents: int | None
    flag_usage_drop: bool | None
    flag_usage_spike: bool | None
    flag_canceled: bool | None


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")      # a client cannot send org_id
    user_id: UUID | None = None
    feature: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    occurred_at: dt.datetime
    event_key: str = Field(min_length=8, max_length=128)

    @field_validator("occurred_at")
    @classmethod
    def _aware_and_not_future(cls, v):
        if v.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if v > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
            raise ValueError("occurred_at is in the future")
        return v


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[EventIn] = Field(min_length=1, max_length=500)


class IngestResult(BaseModel):
    received: int
    inserted: int
    duplicates: int


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)