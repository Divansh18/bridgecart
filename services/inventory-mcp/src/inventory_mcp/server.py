"""Internal, static demo inventory MCP service; no database or store access."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVENTORY_MCP_", extra="ignore")
    host: str = "127.0.0.1"
    port: int = Field(default=8002, ge=1, le=65535)
    bearer_token: SecretStr

    @field_validator("bearer_token")
    @classmethod
    def require_strong_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("bearer token must be at least 32 characters")
        return value


DEMO_STOCK = {
    "BRIDGECART-DEMO-001": {"available": 12, "warehouse": "BLR-DEMO"},
    "BRIDGECART-MCP-TEST-001": {"available": 7, "warehouse": "BLR-DEMO"},
}


def create_mcp() -> MCPServer:
    mcp = MCPServer(
        "BridgeCart Demo Inventory",
        instructions="Seeded demo stock, not live WooCommerce inventory.",
    )

    @mcp.tool(
        description="Look up seeded demo stock by exact SKU; no reservation or live sync.",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    async def lookup_inventory(sku: str) -> dict[str, object]:
        if (
            not sku
            or len(sku) > 80
            or not sku.isascii()
            or not all(c.isalnum() or c in "-_" for c in sku)
        ):
            raise ToolError("sku must be 1-80 ASCII letters, digits, hyphens, or underscores")
        row = DEMO_STOCK.get(sku)
        if row is None:
            return {"sku": sku, "found": False}
        return {
            "sku": sku,
            "found": True,
            "available": row["available"],
            "warehouse": row["warehouse"],
            "source": "seeded_demo",
        }

    return mcp


class BearerGuard:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app, self.token = app, token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            supplied = next(
                (
                    value.decode("latin1")
                    for key, value in scope["headers"]
                    if key.lower() == b"authorization"
                ),
                "",
            )
            if not secrets.compare_digest(supplied, "Bearer " + self.token):
                await Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


def create_app(settings: Settings) -> ASGIApp:
    mcp = create_mcp()

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/health/live", lambda _: JSONResponse({"status": "live"})),
            Route("/health/ready", lambda _: JSONResponse({"status": "ready"})),
            Mount(
                "/",
                app=mcp.streamable_http_app(
                    transport_security=TransportSecuritySettings(
                        enable_dns_rebinding_protection=False
                    ),
                    stateless_http=True,
                ),
            ),
        ],
        lifespan=lifespan,
    )
    return BearerGuard(app, settings.bearer_token.get_secret_value())


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
