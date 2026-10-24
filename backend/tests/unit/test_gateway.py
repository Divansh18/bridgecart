"""Audit persistence, cancellation, and bounded transport behavior."""

import asyncio

import httpx2
import pytest
from mcp.types import CallToolResult, TextContent, Tool

from bridgecart.auth.dependencies import ApiKeyActor
from bridgecart.auth.models import ApiKey, User
from bridgecart.core.config import Settings
from bridgecart.gateway.models import ToolAudit, UpstreamServer
from bridgecart.gateway.service import Discovery, Gateway, GatewayFailure, exposed_name
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


def audit_gateway(
    monkeypatch: pytest.MonkeyPatch, *, finalization_fails: bool = True
) -> tuple[Gateway, ApiKeyActor, str, list[ToolAudit]]:
    user = User(id=1, email="member@example.com", password_hash="unused", role="member", active=True)
    key = ApiKey(id=2, user_id=1, created_by=1, name="test", token_hash="unused", prefix="bck_")
    server = UpstreamServer(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        name="Test MCP",
        url="http://test-mcp:8001/mcp",
        enabled=True,
        auth_type="none",
    )
    public = exposed_name(server.id, "write_item")
    audit_rows: list[ToolAudit] = []
    sessions = 0

    class Session:
        def __init__(self, number: int) -> None:
            self.number = number

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        async def execute(self, *_args):  # type: ignore[no-untyped-def]
            class Result:
                def one_or_none(self):  # type: ignore[no-untyped-def]
                    return key, user

            return Result()

        async def get(self, model, _identifier):  # type: ignore[no-untyped-def]
            return server if model is UpstreamServer else audit_rows[0]

        def add(self, row: ToolAudit) -> None:
            row.id = 1
            audit_rows.append(row)

        async def commit(self) -> None:
            if self.number == 5 and finalization_fails:
                raise RuntimeError("private database failure")

    def factory() -> Session:
        nonlocal sessions
        sessions += 1
        return Session(sessions)

    gateway = Gateway(Settings(database_url="postgresql+asyncpg://user:pass@localhost/db"), factory)  # type: ignore[arg-type]

    async def discover(_server: UpstreamServer) -> Discovery:
        tool = Tool(name="write_item", inputSchema={"type": "object", "properties": {}})
        return Discovery({public: tool}, "Connected", None, 0)

    monkeypatch.setattr(gateway, "discover", discover)
    return gateway, ApiKeyActor(user, key), public, audit_rows


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream", ["success", "error", "timeout"])
async def test_audit_finalization_failure_preserves_upstream_outcome(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, upstream: str
) -> None:
    gateway, actor, public, audits = audit_gateway(monkeypatch)
    calls = 0

    async def connect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if upstream == "error":
            raise GatewayFailure("upstream_tool_error", "Upstream tool returned an error")
        if upstream == "timeout":
            raise GatewayFailure("timeout", "Upstream timed out; a write may have completed")
        return CallToolResult(content=[TextContent(type="text", text="item created")])

    monkeypatch.setattr(gateway, "_connect", connect)
    result = await gateway.execute(actor, public, {})
    assert result.is_error
    assert "private database failure" not in result.content[0].text
    assert "audit finalization" in result.content[0].text.lower()
    assert calls == 1  # An uncertain write must not be retried.
    assert audits[0].outcome == {"success": "success", "error": "upstream_error", "timeout": "timeout"}[upstream]
    assert "gateway_audit_finalize_failed" in caplog.text
    assert "private database failure" not in caplog.text
    assert "item created" not in caplog.text
    if upstream == "success":
        assert "Upstream reported success" in result.content[0].text
    elif upstream == "error":
        assert "Upstream tool returned an error" in result.content[0].text
    else:
        assert "may have completed" in result.content[0].text


@pytest.mark.asyncio
async def test_external_tool_audit_and_logs_have_safe_correlation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gateway, actor, public, audits = audit_gateway(monkeypatch, finalization_fails=False)

    async def connect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return CallToolResult(content=[TextContent(type="text", text="private result payload")])

    monkeypatch.setattr(gateway, "_connect", connect)
    with caplog.at_level("INFO", logger="bridgecart.gateway.service"):
        result = await gateway.execute(actor, public, {"private_argument": "private value"})
    assert not result.is_error
    assert audits[0].correlation_id is not None
    assert len(audits[0].correlation_id) == 36
    assert audits[0].outcome == "success"
    assert f"correlation_id={audits[0].correlation_id}" in caplog.text
    assert "outcome=success" in caplog.text
    assert "private result payload" not in caplog.text
    assert "private value" not in caplog.text


@pytest.mark.asyncio
async def test_cancellation_propagates_even_when_audit_finalization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, actor, public, audits = audit_gateway(monkeypatch)
    entered = asyncio.Event()

    async def connect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(gateway, "_connect", connect)
    task = asyncio.create_task(gateway.execute(actor, public, {}))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert audits[0].outcome == "interrupted"


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
