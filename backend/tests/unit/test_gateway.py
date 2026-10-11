"""Fail-closed audit behavior without any upstream dispatch."""

import httpx2
import pytest

from bridgecart.auth.dependencies import ApiKeyActor
from bridgecart.auth.models import ApiKey, User
from bridgecart.core.config import Settings
from bridgecart.gateway.service import Gateway
from bridgecart.gateway.transport import (
    MAX_WIRE_BYTES,
    LimitedStream,
    LimitedTransport,
    ResponseTooLarge,
    UpstreamRedirect,
)


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
async def test_authentication_database_failure_has_safe_error() -> None:
    user = User(id=1, email="member@example.com", password_hash="unused", role="member", active=True)
    key = ApiKey(id=2, user_id=1, created_by=1, name="test", token_hash="unused", prefix="bck_")

    class Broken:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        async def execute(self, *_args):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret database connection detail")

    gateway = Gateway(
        Settings(database_url="postgresql+asyncpg://user:pass@localhost/db"),
        lambda: Broken(),  # type: ignore[arg-type]
    )
    result = await gateway.execute(ApiKeyActor(user=user, key=key), "unknown", {})
    assert result.is_error
    assert "secret database" not in result.content[0].text


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


@pytest.mark.asyncio
async def test_upstream_redirect_is_rejected_before_sdk_replay() -> None:
    transport = LimitedTransport()
    transport.inner = httpx2.MockTransport(
        lambda _request: httpx2.Response(307, headers={"location": "http://169.254.169.254/mcp"})
    )
    with pytest.raises(UpstreamRedirect):
        await transport.handle_async_request(httpx2.Request("POST", "http://bridgecart-inventory-mcp:8002/mcp"))
