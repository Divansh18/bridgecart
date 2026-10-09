from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRIDGECART_", env_file=".env", extra="ignore")

    database_url: PostgresDsn
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    database_connect_timeout: float = Field(default=2.0, gt=0, le=30)

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("database_url must use postgresql+asyncpg")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return level


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
