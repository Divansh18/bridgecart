import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from woocommerce_mcp.client import StoreError, WooClient
from woocommerce_mcp.config import Settings
from woocommerce_mcp.validation import (
    order_dates,
    order_status,
    pagination,
    positive_id,
    product_input,
)

PRODUCT_PATH = "/wp-json/wc/v3/products"
ORDER_PATH = "/wp-json/wc/v3/orders"


def _product(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("id", "name", "status", "regular_price", "price", "permalink")
    }


def _order(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in ("id", "status", "date_created", "total", "currency")} | {
        "line_items": [
            {key: line.get(key) for key in ("product_id", "name", "quantity", "total")}
            for line in item.get("line_items", [])
        ]
    }


def create_mcp(client: WooClient) -> MCPServer:
    mcp = MCPServer(
        "BridgeCart WooCommerce",
        instructions="Store tools use a dedicated API key. Annotations do not grant access.",
    )

    async def call(
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[Any, int]:
        try:
            return await client.request(method, path, params=params, body=body)
        except StoreError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        description="List products with bounded pagination and optional search.",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def list_products(
        page: int = 1, per_page: int = 20, search: str | None = None
    ) -> dict[str, Any]:
        params = pagination(page, per_page)
        if search is not None:
            if len(search) > 200:
                raise ToolError("search must be at most 200 characters")
            params["search"] = search
        data, total = await call("GET", PRODUCT_PATH, params=params)
        return {
            "products": [_product(item) for item in data],
            "page": page,
            "per_page": per_page,
            "total": total,
        }

    @mcp.tool(
        description="Create a published simple product with a non-negative decimal-string price.",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def create_product(name: str, price: str) -> dict[str, Any]:
        data, _ = await call("POST", PRODUCT_PATH, body=product_input(name, price))
        return {"id": data["id"], "public_url": data["permalink"]}

    @mcp.tool(
        description="List orders without contact details. today uses Asia/Kolkata; dates use ISO.",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def list_orders(
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        today: bool = False,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        params = pagination(page, per_page) | order_dates(today, after, before)
        if status is not None:
            params["status"] = order_status(status)
        data, total = await call("GET", ORDER_PATH, params=params)
        return {
            "orders": [_order(item) for item in data],
            "page": page,
            "per_page": per_page,
            "total": total,
        }

    @mcp.tool(
        description="Get one order by positive ID, omitting customer contact and address fields.",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def get_order(order_id: int) -> dict[str, Any]:
        data, _ = await call("GET", f"{ORDER_PATH}/{positive_id(order_id)}")
        return _order(data)

    @mcp.tool(
        description="Update one order to a supported WooCommerce status.",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
        ),
    )
    async def update_order_status(order_id: int, status: str) -> dict[str, Any]:
        data, _ = await call(
            "PUT", f"{ORDER_PATH}/{positive_id(order_id)}", body={"status": order_status(status)}
        )
        return {"id": data["id"], "status": data["status"]}

    return mcp


class BearerGuard:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

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


def create_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> ASGIApp:
    client = WooClient(settings, transport)
    mcp = create_mcp(client)

    async def live(_: Request) -> Response:
        return JSONResponse({"status": "live"})

    async def ready(_: Request) -> Response:
        try:
            await client.request("GET", PRODUCT_PATH, params={"page": "1", "per_page": "1"})
        except StoreError:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            try:
                yield
            finally:
                await client.close()

    transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = Starlette(
        routes=[
            Route("/health/live", live),
            Route("/health/ready", ready),
            Mount(
                "/",
                app=mcp.streamable_http_app(
                    transport_security=transport_security, stateless_http=True
                ),
            ),
        ],
        lifespan=lifespan,
    )
    return BearerGuard(app, settings.bearer_token.get_secret_value())


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
