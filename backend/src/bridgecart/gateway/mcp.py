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
from bridgecart.gateway.service import Gateway, safe_result

_authorization: ContextVar[str | None] = ContextVar("gateway_authorization", default=None)


async def _actor(factory: async_sessionmaker[AsyncSession]) -> ApiKeyActor:
    async with factory() as db:
        return await authenticate_api_key_actor(_authorization.get(), db)


class ApiKeyGuard:
    def __init__(self, app: ASGIApp, factory: async_sessionmaker[AsyncSession]) -> None:
        self.app, self.factory = app, factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = next(
            (value.decode("latin1") for key, value in scope.get("headers", []) if key.lower() == b"authorization"), None
        )
        try:
            async with self.factory() as db:
                await authenticate_api_key_actor(authorization, db)
        except HTTPException:
            await Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
            return
        token = _authorization.set(authorization)
        try:
            await self.app(scope, receive, send)
        finally:
            _authorization.reset(token)


def create_gateway_mcp(gateway: Gateway, factory: async_sessionmaker[AsyncSession]) -> tuple[Server[Any], ASGIApp]:
    async def list_tools(_ctx: Any, _params: PaginatedRequestParams | None) -> ListToolsResult:
        await _actor(factory)
        return ListToolsResult(tools=await gateway.list_tools())

    async def call_tool(_ctx: Any, params: CallToolRequestParams) -> CallToolResult:
        try:
            actor = await _actor(factory)
        except HTTPException:
            return safe_result("authentication", "API key is no longer valid")
        return await gateway.execute(actor, params.name, params.arguments or {})

    server: Server[Any] = Server("BridgeCart Gateway", on_list_tools=list_tools, on_call_tool=call_tool)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=131072,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return server, ApiKeyGuard(app, factory)
