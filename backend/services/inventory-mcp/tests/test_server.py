import httpx2
import pytest
from mcp.client import Client
from pydantic import SecretStr, ValidationError

from inventory_mcp.server import Settings, create_app, create_mcp


@pytest.mark.asyncio
async def test_inventory_lookup_and_validation() -> None:
    async with Client(create_mcp()) as client:
        result = await client.list_tools()
        assert [tool.name for tool in result.tools] == ["lookup_inventory"]
        found = await client.call_tool("lookup_inventory", {"sku": "BRIDGECART-DEMO-001"})
        unknown = await client.call_tool("lookup_inventory", {"sku": "UNKNOWN"})
        invalid = await client.call_tool("lookup_inventory", {"sku": "../../etc"})
    assert found.structured_content["available"] == 12
    assert unknown.structured_content["found"] is False
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
