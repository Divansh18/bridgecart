"""Internal deterministic demo shipping estimator; not carrier quotes."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation

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
    model_config = SettingsConfigDict(env_prefix="SHIPPING_MCP_", extra="ignore")
    host: str = "127.0.0.1"
    port: int = Field(default=8003, ge=1, le=65535)
    bearer_token: SecretStr

    @field_validator("bearer_token")
    @classmethod
    def require_strong_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("bearer token must be at least 32 characters")
        return value


def create_mcp() -> MCPServer:
    mcp = MCPServer(
        "BridgeCart Demo Shipping",
        instructions="Deterministic Indian demo estimates, not carrier rates.",
    )

    @mcp.tool(
        description="Estimate demo INR shipping by Indian PIN and parcel weight (0.01-20 kg).",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    async def estimate_shipping(
        pin_code: str, weight_kg: str, service_level: str = "standard"
    ) -> dict[str, str]:
        if (
            len(pin_code) != 6
            or not pin_code.isascii()
            or not pin_code.isdigit()
            or pin_code[0] == "0"
        ):
            raise ToolError("pin_code must be a six-digit Indian PIN beginning 1-9")
        if service_level not in {"standard", "express"}:
            raise ToolError("service_level must be standard or express")
        try:
            weight = Decimal(weight_kg)
        except (InvalidOperation, TypeError):
            raise ToolError("weight_kg must be a decimal string") from None
        if (
            not weight.is_finite()
            or weight < Decimal("0.01")
            or weight > Decimal("20")
            or weight != weight.quantize(Decimal("0.01"))
        ):
            raise ToolError("weight_kg must be between 0.01 and 20 with at most two decimal places")
        zone = "south" if pin_code[0] in "567" else "other_india"
        base = Decimal("80") if zone == "south" else Decimal("120")
        charge = base + max(weight - Decimal("1"), Decimal("0")) * Decimal("20")
        if service_level == "express":
            charge += Decimal("100")
        return {
            "pin_code": pin_code,
            "zone": zone,
            "service_level": service_level,
            "currency": "INR",
            "amount": f"{charge:.2f}",
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
