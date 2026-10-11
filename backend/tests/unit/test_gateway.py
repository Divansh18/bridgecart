"""Fail-closed audit behavior without any upstream dispatch."""

import httpx2
import pytest

from bridgecart.auth.dependencies import ApiKeyActor
from bridgecart.auth.models import ApiKey, User
from bridgecart.core.config import Settings
from bridgecart.gateway.service import Gateway
from bridgecart.gateway.transport import MAX_WIRE_BYTES, LimitedStream, ResponseTooLarge


@pytest.mark.asyncio
async def test_audit_insert_failure_prevents_upstream_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(id=1, email="member@example.com", password_hash="unused", role="member", active=True)
    key = ApiKey(id=2, user_id=1, created_by=1, name="test", token_hash="unused", prefix="bck_")

    class Session:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        async def execute(self, *_args):  # type: ignore[no-untyped-def]
            class Result:
                def one_or_none(self):  # type: ignore[no-untyped-def]
                    return key, user

            return Result()

        async def get(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def add(self, *_args):  # type: ignore[no-untyped-def]
            return None

        async def commit(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("database unavailable")

    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db")
    gateway = Gateway(settings, lambda: Session())  # type: ignore[arg-type]
    calls = 0

    async def forbidden_connect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise AssertionError("upstream was contacted")

    monkeypatch.setattr(gateway, "_connect", forbidden_connect)
    outcome = await gateway.execute(ApiKeyActor(user=user, key=key), "unknown", {})
    assert outcome.is_error
    assert "not dispatched" in outcome.content[0].text
    assert calls == 0


@pytest.mark.asyncio
async def test_upstream_stream_is_bounded_before_parsing() -> None:
    class Source(httpx2.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"a" * (MAX_WIRE_BYTES // 2)
            yield b"b" * (MAX_WIRE_BYTES // 2 + 1)

        async def aclose(self) -> None:
            return None

    stream = LimitedStream(Source())
    with pytest.raises(ResponseTooLarge):
        async for _ in stream:
            pass
