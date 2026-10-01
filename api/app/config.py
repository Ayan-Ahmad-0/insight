from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str
    supabase_jwt_secret: str | None = None   # only for legacy HS256 projects
    cors_origins: str = "https://insight-1-g4j1.onrender.com"
    db_pool_max: int = 5
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY", repr=False)
    gemini_model: str = "gemini-3.1-flash-lite"                 # copy the exact string from DocGuide's config
    ai_enabled: bool = True                # global kill switch
    ai_default_daily_budget_usd: float = 0.50
    ai_max_tool_rounds: int = 4
    price_in_per_m: float = 0.25           # copy from DocGuide's cost.py (USD per 1M input tokens)
    price_out_per_m: float = 1.50
    @property
    def issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()