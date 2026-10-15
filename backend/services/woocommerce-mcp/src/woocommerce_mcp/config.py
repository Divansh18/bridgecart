from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WOOCOMMERCE_MCP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    api_base_url: str
    public_url: str
    consumer_key: SecretStr
    consumer_secret: SecretStr
    bearer_token: SecretStr
    connect_timeout: float = Field(default=3, gt=0, le=30)
    request_timeout: float = Field(default=8, gt=0, le=60)

    @field_validator("api_base_url", "public_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in ("http", "https")
                and parsed.hostname is not None
                and parsed.port != 0
                and parsed.username is None
                and parsed.password is None
                and parsed.path in ("", "/")
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("must be an absolute root HTTP URL without credentials")
        return value.rstrip("/")

    @field_validator("consumer_key", "consumer_secret", "bearer_token")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("credential must not be empty")
        return value
