from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    qloo_api_key: SecretStr | None = None
    qloo_base_url: Literal["https://hackathon.api.qloo.com"] = "https://hackathon.api.qloo.com"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://tasteshift:tasteshift@localhost:5432/tasteshift"
    )
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False
    qloo_timeout: float = Field(default=8, gt=0, le=30)
    discovery_timeout: float = Field(default=25, gt=0, le=60)
    session_days: int = Field(default=30, ge=1, le=90)
