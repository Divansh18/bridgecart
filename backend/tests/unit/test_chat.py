"""Delegation and deterministic Claude tool-loop checks."""

import base64
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from mcp.types import CallToolResult, TextContent, Tool

from bridgecart.auth.dependencies import SessionActor
from bridgecart.auth.models import LoginSession, User
from bridgecart.chat import service
from bridgecart.core.config import Settings
from bridgecart.gateway.delegation import authenticate_delegation, issue_delegation


def actor() -> SessionActor:
    user = User(id=7, email="member@example.com", password_hash="unused", role="member", active=True)
    session = LoginSession(
        id=11, user_id=7, token_hash="hash", csrf_hash="hash", expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    return SessionActor(user, session)


def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        gateway_enabled=True,
        upstream_encryption_key=Fernet.generate_key().decode(),
        gateway_allowed_urls="http://bridgecart-woocommerce-mcp:8001/mcp",
        claude_model="claude-sonnet-4-6",
    )


def test_delegation_is_short_lived_and_signed() -> None:
    configuration = settings()
    token = issue_delegation(configuration, actor(), "00000000-0000-0000-0000-000000000001")
    assert token.startswith("bcd_")
    assert "member@example.com" not in token
    encoded = token[4:].split(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert payload["u"] == 7 and payload["s"] == 11
    assert 0 < payload["e"] - int(time.time()) <= 120


@pytest.mark.asyncio
async def test_expired_or_tampered_delegation_is_rejected_before_database() -> None:
    configuration = settings()
    subject = actor()
    subject.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = issue_delegation(configuration, subject, "00000000-0000-0000-0000-000000000001")
    with pytest.raises(HTTPException) as error:
        await authenticate_delegation(expired, configuration, None)  # type: ignore[arg-type]
    assert error.value.status_code == 401
    subject.session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    token = issue_delegation(configuration, subject, "00000000-0000-0000-0000-000000000001")
    with pytest.raises(HTTPException) as error:
        await authenticate_delegation(token[:-1] + ("A" if token[-1] != "A" else "B"), configuration, None)  # type: ignore[arg-type]
    assert error.value.status_code == 401


class FakeSession:
    def __init__(self, tools: list[Tool], results: list[CallToolResult]) -> None:
        self.tools, self.results = tools, results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> Any:
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any], **_kwargs: object) -> CallToolResult:
        self.calls.append((name, arguments))
        return self.results.pop(0)


class FakeProvider:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def tool_use(identifier: str, name: str, arguments: Any = None) -> Any:
    return SimpleNamespace(type="tool_use", id=identifier, name=name, input=arguments if arguments is not None else {})


def reply(text: str) -> Any:
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def app_with_provider(configuration: Settings, provider: FakeProvider) -> Any:
    return SimpleNamespace(state=SimpleNamespace(settings=configuration, chat_client=provider))


def install_fake_gateway(monkeypatch: pytest.MonkeyPatch, fake: FakeSession) -> None:
    @asynccontextmanager
    async def fake_transport(*_args: Any, **_kwargs: Any):  # type: ignore[no-untyped-def]
        yield None, None

    async def names(*_args: Any) -> dict[str, str]:
        return {"0" * 32: "WooCommerce", "1" * 32: "Inventory"}

    monkeypatch.setattr(service, "streamable_http_client", fake_transport)
    monkeypatch.setattr(service, "ClientSession", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(service, "_server_names", names)


@pytest.mark.asyncio
async def test_multiple_tools_preserve_use_result_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = "bc_" + "0" * 32 + "_" + "a" * 24, "bc_" + "1" * 32 + "_" + "b" * 24
    fake = FakeSession(
        [Tool(name=first, inputSchema={"type": "object"}), Tool(name=second, inputSchema={"type": "object"})],
        [
            CallToolResult(content=[TextContent(type="text", text="product created")]),
            CallToolResult(content=[TextContent(type="text", text="demo stock")]),
        ],
    )
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider(
        [
            SimpleNamespace(stop_reason="tool_use", content=[tool_use("toolu_1", first), tool_use("toolu_2", second)]),
            reply("Done"),
        ]
    )
    result = await service.chat_turn(app_with_provider(settings(), provider), actor(), "Use both tools", [])
    assert result["reply"] == "Done"
    assert [trace["server"] for trace in result["traces"]] == ["WooCommerce", "Inventory"]
    sent = provider.requests[1]["messages"][-1]["content"]
    assert [item["tool_use_id"] for item in sent] == ["toolu_1", "toolu_2"]
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_uncertain_write_stops_before_provider_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "bc_" + "0" * 32 + "_" + "a" * 24
    fake = FakeSession(
        [Tool(name=name, inputSchema={"type": "object"})],
        [
            CallToolResult(
                content=[TextContent(type="text", text="Upstream timed out; a write may have completed")], is_error=True
            )
        ],
    )
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider([SimpleNamespace(stop_reason="tool_use", content=[tool_use("toolu_1", name)])])
    result = await service.chat_turn(app_with_provider(settings(), provider), actor(), "Create product", [])
    assert result["traces"][0]["status"] == "uncertain"
    assert "Check the store" in result["reply"]
    assert len(provider.requests) == 1 and len(fake.calls) == 1


@pytest.mark.asyncio
async def test_tool_call_limit_prevents_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "bc_" + "0" * 32 + "_" + "a" * 24
    fake = FakeSession([Tool(name=name, inputSchema={"type": "object"})], [])
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider(
        [SimpleNamespace(stop_reason="tool_use", content=[tool_use(str(i), name) for i in range(9)])]
    )
    with pytest.raises(HTTPException, match="Chat tool limit reached"):
        await service.chat_turn(app_with_provider(settings(), provider), actor(), "too many", [])
    assert fake.calls == []


@pytest.mark.asyncio
async def test_truncated_response_does_not_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSession([], [])
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider([SimpleNamespace(stop_reason="max_tokens", content=[])])
    with pytest.raises(HTTPException, match="truncated"):
        await service.chat_turn(app_with_provider(settings(), provider), actor(), "question", [])
    assert fake.calls == []


@pytest.mark.asyncio
async def test_tool_error_is_returned_to_claude_and_not_claimed_success(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "bc_" + "0" * 32 + "_" + "a" * 24
    fake = FakeSession(
        [Tool(name=name, title="lookup_inventory", inputSchema={"type": "object"})],
        [CallToolResult(content=[TextContent(type="text", text="Server is disabled")], is_error=True)],
    )
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider(
        [SimpleNamespace(stop_reason="tool_use", content=[tool_use("toolu_3", name)]), reply("Unavailable")]
    )
    result = await service.chat_turn(app_with_provider(settings(), provider), actor(), "lookup", [])
    assert result["traces"][0]["status"] == "error"
    assert result["traces"][0]["tool"] == "lookup_inventory"
    tool_result = provider.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True and tool_result["tool_use_id"] == "toolu_3"


@pytest.mark.asyncio
async def test_invalid_arguments_reach_gateway_rejection_path(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "bc_" + "0" * 32 + "_" + "a" * 24
    fake = FakeSession(
        [Tool(name=name, inputSchema={"type": "object"})],
        [CallToolResult(content=[TextContent(type="text", text="Tool arguments are invalid")], is_error=True)],
    )
    install_fake_gateway(monkeypatch, fake)
    provider = FakeProvider(
        [SimpleNamespace(stop_reason="tool_use", content=[tool_use("toolu_4", name, "bad")]), reply("Invalid")]
    )
    await service.chat_turn(app_with_provider(settings(), provider), actor(), "lookup", [])
    assert fake.calls == [(name, {"__bridgecart_invalid_arguments__": True})]
