import pytest
from mcp.client import Client

from shipping_mcp.server import mcp


@pytest.mark.asyncio
async def test_server_advertises_no_business_tools() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()
    assert result.tools == []
