"""Streamable HTTP gateway with per-request and per-call API-key checks."""

from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException
from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from bridgecart.auth.dependencies import ApiKeyActor, authenticate_api_key_actor
from bridgecart.core.config import Settings
from bridgecart.gateway.delegation import DelegatedActor, authenticate_delegation
from bridgecart.gateway.service import Gateway, safe_result

_authorization: ContextVar[str | None] = ContextVar("gateway_authorization", default=None)


async def _actor(factory: async_sessionmaker[AsyncSession], settings: Settings) -> ApiKeyActor | DelegatedActor:
    async with factory() as db:
        authorization = _authorization.get()
        if authorization and authorization.startswith("Bearer bcd_"):
            return await authenticate_delegation(authorization.removeprefix("Bearer "), settings, db)
        return await authenticate_api_key_actor(authorization, db)


class GatewayGuard:
    def __init__(self, app: ASGIApp, factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.app, self.factory, self.settings = app, factory, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = next(
            (value.decode("latin1") for key, value in scope.get("headers", []) if key.lower() == b"authorization"), None
        )
        if authorization and authorization.startswith("Bearer bcd_"):
            client = scope.get("client")
            if not client or client[0] not in {"127.0.0.1", "::1"}:
                await Response(status_code=401)(scope, receive, send)
                return
        try:
            async with self.factory() as db:
                if authorization and authorization.startswith("Bearer bcd_"):
                    await authenticate_delegation(authorization.removeprefix("Bearer "), self.settings, db)
                else:
                    await authenticate_api_key_actor(authorization, db)
        except HTTPException:
            await Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
            return
        except Exception:
            await Response(status_code=503)(scope, receive, send)
            return
        token = _authorization.set(authorization)
        try:
            await self.app(scope, receive, send)
        finally:
            _authorization.reset(token)


def create_gateway_mcp(gateway: Gateway, factory: async_sessionmaker[AsyncSession]) -> tuple[Server[Any], ASGIApp]:
    async def list_tools(_ctx: Any, _params: PaginatedRequestParams | None) -> ListToolsResult:
        try:
            await _actor(factory, gateway.settings)
            return ListToolsResult(tools=await gateway.list_tools())
        except HTTPException:
            raise RuntimeError("API key is no longer valid") from None
        except Exception:
            raise RuntimeError("Gateway registry is unavailable") from None

    async def call_tool(_ctx: Any, params: CallToolRequestParams) -> CallToolResult:
        try:
            actor = await _actor(factory, gateway.settings)
        except HTTPException:
            return safe_result("authentication", "API key is no longer valid")
        except Exception:
            return safe_result("authentication_unavailable", "Gateway authentication is unavailable")
        return await gateway.execute(actor, params.name, params.arguments or {})

    server: Server[Any] = Server("BridgeCart Gateway", on_list_tools=list_tools, on_call_tool=call_tool)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=131072,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return server, GatewayGuard(app, factory, gateway.settings)
