import pytest
from pydantic import ValidationError

from bridgecart.core.config import Settings


def test_database_url_must_use_asyncpg() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://user:pass@localhost/db")


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRIDGECART_DATABASE_URL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_log_level_is_normalized() -> None:
    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db", log_level="warning")
    assert settings.log_level == "WARNING"
