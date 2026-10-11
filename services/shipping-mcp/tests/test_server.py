import httpx2
import pytest
from mcp.client import Client
from pydantic import SecretStr, ValidationError

from shipping_mcp.server import Settings, create_app, create_mcp


@pytest.mark.asyncio
async def test_shipping_estimate_and_validation() -> None:
    async with Client(create_mcp()) as client:
        result = await client.list_tools()
        assert [tool.name for tool in result.tools] == ["estimate_shipping"]
        estimate = await client.call_tool(
            "estimate_shipping", {"pin_code": "560001", "weight_kg": "1.50"}
        )
        invalid = await client.call_tool(
            "estimate_shipping", {"pin_code": "000000", "weight_kg": "1"}
        )
    assert estimate.structured_content["amount"] == "90.00"
    assert invalid.is_error


@pytest.mark.asyncio
async def test_streamable_http_rejects_missing_and_invalid_bearer() -> None:
    app = create_app(Settings(bearer_token=SecretStr("x" * 32)))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/mcp", json={})).status_code == 401
        assert (
            await client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={})
        ).status_code == 401
    with pytest.raises(ValidationError):
        Settings(bearer_token=SecretStr("short"))
