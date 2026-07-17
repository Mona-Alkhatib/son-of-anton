from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: SecretStr
    openai_api_key: SecretStr | None = None
    database_url: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="ANTON_LOG_LEVEL"
    )
    default_model: str = "claude-sonnet-4-6"
    per_incident_budget_usd: float = 0.50


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
