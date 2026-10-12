"""Bounded upstream discovery and one shared authenticated tool execution path."""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, PaginatedRequestParams, TextContent, Tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bridgecart.auth.dependencies import ApiKeyActor
from bridgecart.auth.models import ApiKey, LoginSession, User, utc_now
from bridgecart.core.config import Settings
from bridgecart.gateway.delegation import DelegatedActor
from bridgecart.gateway.models import ToolAudit, UpstreamServer
from bridgecart.gateway.security import cipher
from bridgecart.gateway.transport import LimitedTransport, ResponseTooLarge, UpstreamRedirect

MAX_TOOLS = 50
MAX_SCHEMA_BYTES = 65536
MAX_RESULT_BYTES = 524288
MAX_ARGUMENT_BYTES = 65536


class GatewayFailure(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def exposed_name(server_id: str, original: str) -> str:
    # 3 + 32 UUID hex + 1 + 24 SHA-256 hex = 60 ASCII characters.
    return "bc_" + server_id.replace("-", "") + "_" + hashlib.sha256(original.encode()).hexdigest()[:24]


def safe_result(category: str, message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


@dataclass
class Discovery:
    tools: dict[str, Tool]
    status: str
    reason: str | None
    expires: float


class Gateway:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.factory = factory
        self._cache: dict[str, Discovery] = {}
        self._semaphore = asyncio.Semaphore(4)

    def invalidate(self, server_id: str) -> None:
        self._cache.pop(server_id, None)

    def _headers(self, server: UpstreamServer) -> dict[str, str]:
        if server.auth_type == "none":
            return {}
        if server.credential_encrypted is None:
            raise GatewayFailure("configuration", "Upstream credential is unavailable")
        try:
            secret = cipher(self.settings).decrypt(server.credential_encrypted).decode()
        except Exception as exc:
            raise GatewayFailure("configuration", "Upstream credential cannot be decrypted") from exc
        if server.auth_type == "bearer":
            return {"Authorization": "Bearer " + secret}
        if server.auth_type == "header" and server.header_name:
            return {server.header_name: secret}
        raise GatewayFailure("configuration", "Upstream authentication configuration is invalid")

    async def _connect(
        self, server: UpstreamServer, operation: str, name: str = "", args: dict[str, Any] | None = None
    ) -> Any:
        timeout = (
            self.settings.gateway_discovery_timeout if operation == "discover" else self.settings.gateway_call_timeout
        )
        headers = self._headers(server)
        try:
            async with asyncio.timeout(timeout):
                async with httpx2.AsyncClient(
                    headers=headers,
                    timeout=httpx2.Timeout(timeout, connect=min(timeout, 3.0)),
                    transport=LimitedTransport(),
                    follow_redirects=False,
                    trust_env=False,
                ) as http:
                    async with streamable_http_client(
                        server.url,
                        http_client=http,
                        terminate_on_close=False,
                    ) as (read, write):
                        async with ClientSession(read, write, read_timeout_seconds=timeout) as session:
                            await session.initialize()
                            if operation == "call":
                                return await session.call_tool(name, args or {}, read_timeout_seconds=timeout)
                            found: list[Tool] = []
                            cursor: str | None = None
                            for _ in range(5):
                                page = await session.list_tools(
                                    params=PaginatedRequestParams(cursor=cursor) if cursor else None
                                )
                                found.extend(page.tools)
                                if len(found) > MAX_TOOLS:
                                    raise GatewayFailure("limits", "Upstream exposes too many tools")
                                cursor = page.next_cursor
                                if cursor is None:
                                    return found
                            raise GatewayFailure("limits", "Upstream tool pagination exceeded limit")
        except TimeoutError as exc:
            raise GatewayFailure("timeout", "Upstream timed out; a write may have completed") from exc
        except ResponseTooLarge as exc:
            raise GatewayFailure("limits", "Upstream response exceeds wire-size limit") from exc
        except UpstreamRedirect as exc:
            raise GatewayFailure("redirect", "Upstream redirect is not permitted") from exc
        except GatewayFailure:
            raise
        except Exception as exc:
            # SDK/HTTP exception strings may contain URLs, headers or raw server text.
            raise GatewayFailure("upstream_unavailable", "Upstream MCP service is unavailable") from exc

    async def discover(self, server: UpstreamServer) -> Discovery:
        cached = self._cache.get(server.id)
        if cached and cached.expires > time.monotonic():
            return cached
        async with self._semaphore:
            cached = self._cache.get(server.id)
            if cached and cached.expires > time.monotonic():
                return cached
            try:
                tools = await self._connect(server, "discover")
                mapped: dict[str, Tool] = {}
                for tool in tools:
                    if not tool.name or len(tool.name) > 200:
                        raise GatewayFailure("limits", "Invalid upstream tool name")
                    if len(json.dumps(tool.input_schema).encode()) > MAX_SCHEMA_BYTES:
                        raise GatewayFailure("limits", "Upstream tool schema is too large")
                    public = exposed_name(server.id, tool.name)
                    if public in mapped:
                        raise GatewayFailure("collision", "Upstream tool-name collision")
                    mapped[public] = tool.model_copy(update={"description": (tool.description or "")[:2000]})
                result = Discovery(mapped, "Connected", None, time.monotonic() + self.settings.gateway_cache_seconds)
            except GatewayFailure as exc:
                result = Discovery(
                    {}, "Unreachable", exc.category, time.monotonic() + min(5, self.settings.gateway_cache_seconds)
                )
            self._cache[server.id] = result
            return result

    async def catalog(self) -> list[tuple[UpstreamServer, Discovery]]:
        async with self.factory() as db:
            rows = (await db.scalars(select(UpstreamServer).where(UpstreamServer.removed_at.is_(None)))).all()
        enabled = [row for row in rows if row.enabled]
        found = await asyncio.gather(*(self.discover(row) for row in enabled))
        by_id = {row.id: discovery for row, discovery in zip(enabled, found, strict=True)}
        return [(row, by_id[row.id] if row.enabled else Discovery({}, "Disabled", None, 0)) for row in rows]

    async def list_tools(self) -> list[Tool]:
        return [
            tool.model_copy(update={"name": public})
            for _, discovery in await self.catalog()
            for public, tool in discovery.tools.items()
        ]

    async def execute(
        self, actor: ApiKeyActor | DelegatedActor, public: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        # The shared execution boundary does not trust a previously validated actor.
        try:
            async with self.factory() as db:
                if isinstance(actor, ApiKeyActor):
                    api_query = await db.execute(
                        select(ApiKey, User).join(User, User.id == ApiKey.user_id).where(ApiKey.id == actor.key.id)
                    )
                    api_match = api_query.one_or_none()
                    if (
                        api_match is None
                        or api_match[0].revoked_at is not None
                        or not api_match[1].active
                        or api_match[1].id != actor.user.id
                    ):
                        return safe_result("authentication", "API key is no longer valid")
                    actor = ApiKeyActor(user=api_match[1], key=api_match[0])
                else:
                    session_query = await db.execute(
                        select(LoginSession, User)
                        .join(User, User.id == LoginSession.user_id)
                        .where(LoginSession.id == actor.session_id, User.id == actor.user.id)
                    )
                    session_match = session_query.one_or_none()
                    if (
                        session_match is None
                        or session_match[0].revoked_at is not None
                        or session_match[0].expires_at <= utc_now()
                        or not session_match[1].active
                    ):
                        return safe_result("authentication", "Delegated session is no longer valid")
                    actor = DelegatedActor(session_match[1], session_match[0].id, actor.correlation_id)
        except Exception:
            return safe_result("authentication_unavailable", "Gateway authentication is unavailable")
        started = time.monotonic()
        server_id = public[3:35]
        server: UpstreamServer | None = None
        if public.startswith("bc_") and len(server_id) == 32:
            try:
                import uuid

                server_id = str(uuid.UUID(hex=server_id))
            except ValueError:
                server_id = ""
        else:
            server_id = ""
        try:
            async with self.factory() as db:
                if server_id:
                    server = await db.get(UpstreamServer, server_id)
                audit = ToolAudit(
                    user_id=actor.user.id,
                    user_email=actor.user.email,
                    api_key_id=actor.key.id if isinstance(actor, ApiKeyActor) else None,
                    session_id=actor.session_id if isinstance(actor, DelegatedActor) else None,
                    credential_type="session_delegation" if isinstance(actor, DelegatedActor) else "api_key",
                    correlation_id=actor.correlation_id if isinstance(actor, DelegatedActor) else None,
                    server_id=server.id if server else None,
                    server_name=server.name if server else None,
                    original_tool_name=None,
                    exposed_tool_name=public[:200],
                    started_at=utc_now(),
                    outcome="started",
                )
                db.add(audit)
                await db.commit()  # Fail closed before any upstream dispatch.
                audit_id = audit.id
        except Exception:
            return safe_result("audit_unavailable", "Audit storage unavailable; call was not dispatched")

        outcome = "rejected"
        category: str | None = "unknown_tool"
        try:
            if server is None or server.removed_at is not None:
                raise GatewayFailure("unknown_tool", "Tool is unavailable")
            if not server.enabled:
                raise GatewayFailure("disabled", "Server is disabled")
            discovery = await self.discover(server)
            original = discovery.tools.get(public)
            if original is None:
                raise GatewayFailure("unknown_tool", "Tool is unavailable")
            if len(json.dumps(arguments).encode()) > MAX_ARGUMENT_BYTES:
                raise GatewayFailure("limits", "Tool arguments exceed size limit")
            if arguments.get("__bridgecart_invalid_arguments__") is True:
                raise GatewayFailure("invalid_arguments", "Tool arguments are invalid")
            # Recheck registry state after discovery; edits and disable take effect on cached calls.
            async with self.factory() as db:
                current_server = await db.get(UpstreamServer, server.id)
                if current_server is None or current_server.removed_at is not None or not current_server.enabled:
                    raise GatewayFailure("disabled", "Server is disabled or removed")
                server = current_server
            async with self.factory() as db:
                try:
                    row = await db.get(ToolAudit, audit_id)
                    if row is None:
                        raise GatewayFailure("audit_unavailable", "Audit storage unavailable; call was not dispatched")
                    row.original_tool_name = original.name[:200]
                    await db.commit()
                except GatewayFailure:
                    raise
                except Exception as exc:
                    raise GatewayFailure(
                        "audit_unavailable", "Audit storage unavailable; call was not dispatched"
                    ) from exc
            result = await self._connect(server, "call", original.name, arguments)
            if not isinstance(result, CallToolResult):
                raise GatewayFailure("upstream_tool_error", "Unsupported upstream tool result")
            if len(result.model_dump_json().encode()) > MAX_RESULT_BYTES:
                raise GatewayFailure("limits", "Upstream tool result exceeds size limit")
            if result.is_error:
                # Do not pass raw upstream errors: they may contain PII or secrets.
                raise GatewayFailure("upstream_tool_error", "Upstream tool returned an error")
            outcome, category = "success", None
        except GatewayFailure as exc:
            outcome = (
                "timeout"
                if exc.category == "timeout"
                else "rejected"
                if exc.category in {"unknown_tool", "disabled", "limits", "audit_unavailable"}
                else "upstream_error"
            )
            category = exc.category
            result = safe_result(exc.category, str(exc))
        except asyncio.CancelledError:
            outcome, category = "interrupted", "cancelled"
            raise
        except Exception:
            outcome, category = "upstream_error", "internal"
            result = safe_result("internal", "Gateway could not complete the call")
        finally:
            try:
                async with self.factory() as db:
                    row = await db.get(ToolAudit, audit_id)
                    if row:
                        row.duration_ms = round((time.monotonic() - started) * 1000)
                        row.outcome = outcome
                        row.error_category = category
                        await db.commit()
            except Exception:
                return safe_result("audit_finalize_failed", "Audit finalization failed; call outcome may be uncertain")
        return result
