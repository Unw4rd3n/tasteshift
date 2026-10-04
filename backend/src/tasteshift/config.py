from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
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
    gemini_api_key: SecretStr | None = None
    model_name: str = Field(
        default="gemini-3.5-flash-lite", pattern=r"^gemini-[A-Za-z0-9_.-]{1,110}$"
    )
    agent_request_limit: int = Field(default=4, ge=1, le=8)
    agent_tool_limit: int = Field(default=6, ge=1, le=12)
    agent_output_tokens: int = Field(default=1200, ge=200, le=4000)
    qloo_attempt_limit: int = Field(default=6, ge=4, le=10)
    agent_concurrency: int = Field(default=2, ge=1, le=4)
    agent_session_runs_per_hour: int = Field(default=10, ge=1, le=30)

    @field_validator("model_name", "gemini_api_key", "qloo_api_key", mode="before")
    @classmethod
    def empty_configuration(cls, value, info: ValidationInfo):
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if info.field_name == "model_name" and (raw is None or not str(raw).strip()):
            return "gemini-3.5-flash-lite"
        if isinstance(raw, str) and not raw.strip():
            return None
        return value
