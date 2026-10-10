from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp.client import Client
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from woocommerce_mcp.client import StoreError, WooClient
from woocommerce_mcp.config import Settings
from woocommerce_mcp.server import create_app, create_mcp
from woocommerce_mcp.validation import (
    order_dates,
    order_status,
    pagination,
    positive_id,
    product_input,
)


def settings() -> Settings:
    return Settings(
        api_base_url="http://wordpress.internal",
        public_url="http://shop.bridgecart.local:8088",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        bearer_token="test-bearer",
    )


def test_configuration_rejects_url_credentials_and_paths() -> None:
    for invalid in ("http://user:pass@wordpress.internal", "http://wordpress.internal/path"):
        with pytest.raises(ValidationError):
            Settings(
                api_base_url=invalid,
                public_url="http://shop.bridgecart.local:8088",
                consumer_key="ck_test",
                consumer_secret="cs_test",
                bearer_token="test-bearer",
            )


def test_validation_and_kolkata_boundaries() -> None:
    assert pagination(1, 50) == {"page": "1", "per_page": "50"}
    assert product_input(" Example ", "12.50")["regular_price"] == "12.50"
    for price in ("-1", "NaN", "Inf", "3.141", "free", "1e2", " 2"):
        with pytest.raises(ToolError):
            product_input("Example", price)
    for page, per_page in ((0, 10), (1, 51), (1001, 1)):
        with pytest.raises(ToolError):
            pagination(page, per_page)
    with pytest.raises(ToolError):
        positive_id(0)
    with pytest.raises(ToolError):
        order_status("invented")
    now = datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Asia/Kolkata"))
    dates = order_dates(True, None, None, now)
    assert dates == {
        "after": "2026-10-09T18:29:59",
        "before": "2026-10-10T18:30:00",
        "dates_are_gmt": "true",
    }
    assert order_dates(False, "2026-10-10", "2026-10-10") == {
        "after": "2026-10-09T23:59:59",
        "before": "2026-10-11T00:00:00",
    }
    with pytest.raises(ToolError):
        order_dates(True, "2026-10-09", None)


@pytest.mark.asyncio
async def test_tool_catalog_and_safe_order_projection() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "wordpress.internal"
        if request.url.path.endswith("/orders/12"):
            return httpx.Response(
                200,
                json={
                    "id": 12,
                    "status": "processing",
                    "billing": {"email": "private@example.com"},
                    "line_items": [
                        {"product_id": 5, "name": "Demo", "quantity": 1, "total": "99.00"}
                    ],
                },
            )
        return httpx.Response(200, json=[], headers={"X-WP-Total": "0"})

    wc = WooClient(settings(), httpx.MockTransport(respond))
    async with Client(create_mcp(wc)) as client:
        listed = await client.list_tools()
        assert {tool.name for tool in listed.tools} == {
            "list_products",
            "create_product",
            "list_orders",
            "get_order",
            "update_order_status",
        }
        result = await client.call_tool("get_order", {"order_id": 12})
        assert not result.is_error
        assert "private@example.com" not in str(result)
        invalid = await client.call_tool("get_order", {"order_id": 0})
        assert invalid.is_error
    await wc.close()


@pytest.mark.asyncio
async def test_rest_errors_and_uncertain_write() -> None:
    for status in (401, 404, 503):
        wc = WooClient(
            settings(),
            httpx.MockTransport(lambda _, status=status: httpx.Response(status, text="private")),
        )
        with pytest.raises(StoreError) as caught:
            await wc.request("GET", "/wp-json/wc/v3/orders/1")
        assert "private" not in str(caught.value)
        await wc.close()

    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret request data")

    wc = WooClient(settings(), httpx.MockTransport(timeout))
    with pytest.raises(StoreError, match="may have succeeded") as caught:
        await wc.request("POST", "/wp-json/wc/v3/products", body={"name": "Test"})
    assert "secret request data" not in str(caught.value)
    await wc.close()


@pytest.mark.asyncio
async def test_oauth_uses_header_and_keeps_secret_out_of_url() -> None:
    def inspect(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("OAuth oauth_consumer_key=")
        assert "oauth_consumer_key" not in request.url.params
        assert "cs_test" not in str(request.url)
        return httpx.Response(200, json=[])

    wc = WooClient(settings(), httpx.MockTransport(inspect))
    await wc.request("GET", "/wp-json/wc/v3/products")
    await wc.close()


@pytest.mark.asyncio
async def test_bearer_guard_and_independent_liveness() -> None:
    app = create_app(settings(), httpx.MockTransport(lambda _: httpx.Response(503)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/mcp", json={})).status_code == 401
        assert (
            await client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={})
        ).status_code == 401
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 503
