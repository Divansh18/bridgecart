from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRIDGECART_", env_file=".env", extra="ignore")

    database_url: PostgresDsn
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    database_connect_timeout: float = Field(default=2.0, gt=0, le=30)
    stage: str = "local"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    invitation_ttl_hours: int = Field(default=72, ge=1, le=168)
    gateway_enabled: bool = False
    upstream_encryption_key: SecretStr | None = None
    gateway_allowed_urls: str = ""
    gateway_discovery_timeout: float = Field(default=5, gt=0, le=30)
    gateway_call_timeout: float = Field(default=12, gt=0, le=60)
    gateway_cache_seconds: float = Field(default=15, ge=0, le=300)

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

    @model_validator(mode="after")
    def validate_cookies(self) -> "Settings":
        if self.stage not in {"local", "production"}:
            raise ValueError("stage must be local or production")
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("cookie_samesite must be lax, strict, or none")
        if (self.stage == "production" or self.cookie_samesite == "none") and not self.cookie_secure:
            raise ValueError("secure cookies are required for this configuration")
        if self.gateway_enabled and (not self.upstream_encryption_key or not self.gateway_allowed_urls):
            raise ValueError("gateway requires encryption key and allowed URLs")
        if self.gateway_enabled and self.upstream_encryption_key:
            try:
                Fernet(self.upstream_encryption_key.get_secret_value().encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("gateway encryption key is invalid") from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
