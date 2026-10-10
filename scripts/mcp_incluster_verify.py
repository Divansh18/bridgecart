#!/usr/bin/env python3
"""Run only in a temporary, network-policy-labeled cluster Pod."""

import asyncio
import json
import os
import sys

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

URL = "http://bridgecart-woocommerce-mcp:8001/mcp"
TOKEN = os.environ["MCP_BEARER_TOKEN"]


async def main() -> None:
    action = sys.argv[1]
    if action == "auth":
        async with httpx2.AsyncClient(timeout=5) as http:
            missing = await http.post(URL, json={})
            invalid = await http.post(URL, headers={"Authorization": "Bearer invalid"}, json={})
        assert missing.status_code == invalid.status_code == 401
        print("Missing and invalid bearer credentials rejected with HTTP 401")
        return
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + TOKEN}, timeout=15) as http:
        async with Client(streamable_http_client(URL, http_client=http)) as client:
                if action == "catalog":
                    tools = await client.list_tools()
                    names = sorted(tool.name for tool in tools.tools)
                    assert names == sorted([
                        "list_products", "create_product", "list_orders", "get_order", "update_order_status"
                    ])
                    by_name = {tool.name: tool for tool in tools.tools}
                    assert by_name["list_products"].annotations.read_only_hint is True
                    assert by_name["create_product"].annotations.read_only_hint is False
                    assert by_name["update_order_status"].annotations.idempotent_hint is False
                    print("MCP initialized; tools:", ", ".join(names))
                    result = await client.call_tool("list_products", {"per_page": 2})
                elif action == "create":
                    result = await client.call_tool("create_product", {"name": sys.argv[2], "price": sys.argv[3]})
                elif action == "orders":
                    result = await client.call_tool("list_orders", {"today": True, "per_page": 20})
                elif action == "get":
                    result = await client.call_tool("get_order", {"order_id": int(sys.argv[2])})
                elif action == "status":
                    result = await client.call_tool("update_order_status", {"order_id": int(sys.argv[2]), "status": sys.argv[3]})
                else:
                    raise ValueError("unknown action")
                assert not result.is_error, result.content
                print(json.dumps(result.structured_content, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
