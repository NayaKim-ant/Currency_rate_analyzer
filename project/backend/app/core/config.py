from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://market_user@127.0.0.1:5432/market_data"
    cors_origins: str = "http://localhost:3000"
    rate_history_days: int = Field(default=365, ge=60, le=3650)
    news_history_days: int = Field(default=90, ge=1, le=3650)
    daily_sync_hour: int = Field(default=6, ge=0, le=23)
    scheduler_timezone: str = "Asia/Seoul"
    job_worker_enabled: bool = True

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
