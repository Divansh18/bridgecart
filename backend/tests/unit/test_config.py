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


def test_anthropic_key_is_optional_and_loaded_without_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-test-value")
    monkeypatch.setenv("BRIDGECART_CLAUDE_MODEL", "chosen-model-id")
    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db", _env_file=None)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "private-test-value"
    assert settings.claude_model == "chosen-model-id"
    assert "private-test-value" not in repr(settings)


def test_blank_claude_model_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+asyncpg://user:pass@localhost/db", claude_model=" ")


def test_blank_anthropic_key_is_rejected_without_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", " ")
    with pytest.raises(ValidationError) as error:
        Settings(database_url="postgresql+asyncpg://user:pass@localhost/db", _env_file=None)
    assert "anthropic_api_key must be non-blank" in str(error.value)
