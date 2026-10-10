from datetime import UTC, datetime
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
    for name in ("", "   ", "x" * 201):
        with pytest.raises(ToolError):
            product_input(name, "1.00")
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
    assert (
        order_dates(True, None, None, datetime(2026, 10, 9, 18, 29, 59, tzinfo=UTC))["after"]
        == "2026-10-08T18:29:59"
    )
    assert (
        order_dates(True, None, None, datetime(2026, 10, 9, 18, 30, tzinfo=UTC))["after"]
        == "2026-10-09T18:29:59"
    )
    with pytest.raises(ToolError):
        order_dates(False, "2026-10-11", "2026-10-10")
    with pytest.raises(ToolError):
        order_dates(False, "not-a-date", None)


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
async def test_list_tools_forward_bounded_filters_and_hide_customer_data() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/products"):
            return httpx.Response(200, json=[], headers={"X-WP-Total": "9"})
        return httpx.Response(
            200,
            json=[{"id": 12, "status": "processing", "billing": {"email": "private@example.com"}}],
            headers={"X-WP-Total": "1"},
        )

    wc = WooClient(settings(), httpx.MockTransport(respond))
    async with Client(create_mcp(wc)) as client:
        products = await client.call_tool(
            "list_products", {"page": 3, "per_page": 7, "search": "demo mug"}
        )
        orders = await client.call_tool(
            "list_orders",
            {
                "page": 2,
                "per_page": 5,
                "status": "processing",
                "after": "2026-10-10",
                "before": "2026-10-10",
            },
        )
    assert not products.is_error and products.structured_content["total"] == 9
    assert not orders.is_error and orders.structured_content["total"] == 1
    assert "private@example.com" not in str(orders)
    assert dict(requests[0].url.params) == {"page": "3", "per_page": "7", "search": "demo mug"}
    assert dict(requests[1].url.params) == {
        "page": "2",
        "per_page": "5",
        "status": "processing",
        "after": "2026-10-09T23:59:59",
        "before": "2026-10-11T00:00:00",
    }
    await wc.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "authentication"), (403, "permission"), (404, "not found"), (503, "unavailable")],
)
async def test_get_order_reports_safe_rest_errors(status: int, expected: str) -> None:
    wc = WooClient(
        settings(),
        httpx.MockTransport(lambda _: httpx.Response(status, text="private customer data")),
    )
    async with Client(create_mcp(wc)) as client:
        result = await client.call_tool("get_order", {"order_id": 12})
    assert result.is_error
    assert expected in str(result).lower()
    assert "private customer data" not in str(result)
    await wc.close()


@pytest.mark.asyncio
async def test_invalid_tool_inputs_never_reach_rest_api() -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid input reached WooCommerce")

    wc = WooClient(settings(), httpx.MockTransport(unexpected))
    async with Client(create_mcp(wc)) as client:
        for name, arguments in (
            ("list_products", {"per_page": 51}),
            ("create_product", {"name": "Demo", "price": "-1"}),
            ("get_order", {"order_id": 0}),
            ("update_order_status", {"order_id": 12, "status": "invented"}),
        ):
            assert (await client.call_tool(name, arguments)).is_error
    await wc.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_write_failure_is_uncertain_and_never_retried(
    method: str, failure: type[httpx.RequestError]
) -> None:
    attempts = 0

    def fail(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise failure("secret request data")

    wc = WooClient(settings(), httpx.MockTransport(fail))
    with pytest.raises(StoreError, match="may have succeeded") as caught:
        await wc.request(method, "/wp-json/wc/v3/products", body={"name": "Test"})
    assert attempts == 1
    assert "secret request data" not in str(caught.value)
    await wc.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("create_product", {"name": "Demo", "price": "12.00"}),
        ("update_order_status", {"order_id": 12, "status": "completed"}),
    ],
)
async def test_write_timeout_is_a_clear_mcp_tool_error(
    tool: str, arguments: dict[str, str | int]
) -> None:
    attempts = 0

    def timeout(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("private request data")

    wc = WooClient(settings(), httpx.MockTransport(timeout))
    async with Client(create_mcp(wc)) as client:
        result = await client.call_tool(tool, arguments)
    assert result.is_error
    assert "may have succeeded" in str(result)
    assert "private request data" not in str(result)
    assert attempts == 1
    await wc.close()


@pytest.mark.asyncio
async def test_read_timeout_is_clear_and_sanitized() -> None:
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret request data")

    wc = WooClient(settings(), httpx.MockTransport(timeout))
    with pytest.raises(StoreError, match="request timed out") as caught:
        await wc.request("GET", "/wp-json/wc/v3/orders")
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
