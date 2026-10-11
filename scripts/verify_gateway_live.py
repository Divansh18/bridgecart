"""Use an external SDK client against the local gateway; never print key material."""

import asyncio
import secrets
import time
from typing import Any

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from verify_backend_live import MEMBER_EMAIL, MEMBER_SECRET, checked, client, kubectl, login, secret_value

MCP_URL = "http://127.0.0.1:8088/mcp"
API_HOST = "api.bridgecart.local"


async def call_as(key: str, names: dict[str, str], *, member: bool = False) -> list[str]:
    async with httpx2.AsyncClient(
        headers={"Host": API_HOST, "Authorization": "Bearer " + key},
        timeout=httpx2.Timeout(15, connect=3),
        trust_env=False,
    ) as http:
        async with streamable_http_client(MCP_URL, http_client=http, terminate_on_close=False) as streams:
            async with ClientSession(*streams, read_timeout_seconds=15) as session:
                await session.initialize()
                listed = await session.list_tools()
                tools = {tool.name for tool in listed.tools}
                assert len(tools) == 7 and set(names.values()) <= tools
                called: list[str] = []
                if not member:
                    products = await session.call_tool(names["list_products"], {"search": "BridgeCart Demo Mug", "per_page": 5})
                    assert not products.is_error and products.structured_content["products"]
                    called.append("list_products")
                    stock = await session.call_tool(names["lookup_inventory"], {"sku": "BRIDGECART-DEMO-001"})
                    assert not stock.is_error and stock.structured_content["available"] == 12
                    called.append("lookup_inventory")
                    quote = await session.call_tool(
                        names["estimate_shipping"], {"pin_code": "560001", "weight_kg": "1.00"}
                    )
                    assert not quote.is_error and quote.structured_content["amount"] == "80.00"
                    called.append("estimate_shipping")
                else:
                    result = await session.call_tool(names["lookup_inventory"], {"sku": "BRIDGECART-DEMO-001"})
                    assert not result.is_error
                    called.append("lookup_inventory")
                return called


def wait_status(admin: httpx.Client, server_id: str, expected: str, timeout: float = 30) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        servers = checked(admin.get("/servers"), 200)
        assert isinstance(servers, list)
        row = next((item for item in servers if item["id"] == server_id), None)
        if row and row["status"] == expected:
            return
        time.sleep(1)
    raise RuntimeError(f"Upstream did not reach {expected} within {timeout}s")


def main() -> None:
    admin_email = secret_value("bridgecart-initial-admin", "admin-email")
    admin_password = secret_value("bridgecart-initial-admin", "admin-password")
    member_password = secret_value(MEMBER_SECRET, "member-password")
    with client() as admin, client() as member:
        admin_csrf = login(admin, admin_email, admin_password)
        member_csrf = login(member, MEMBER_EMAIL, member_password)
        catalog = checked(admin.get("/servers"), 200)
        assert isinstance(catalog, list) and len(catalog) == 3
        assert all(row["status"] == "Connected" for row in catalog)
        names = {tool["original_name"]: tool["name"] for row in catalog for tool in row["tools"]}
        assert len(names) == 7
        admin_key_id = member_key_id = None
        try:
            issued = checked(admin.post(
                "/api-keys", headers={"X-CSRF-Token": admin_csrf},
                json={"name": "milestone4b-verification-" + secrets.token_hex(3)},
            ), 201)
            admin_key_id, admin_key = issued["id"], str(issued["key"])
            issued = checked(member.post(
                "/api-keys", headers={"X-CSRF-Token": member_csrf},
                json={"name": "milestone4b-verification-" + secrets.token_hex(3)},
            ), 201)
            member_key_id, member_key = issued["id"], str(issued["key"])
            bad_body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            with httpx.Client(timeout=5) as anonymous:
                assert anonymous.post(MCP_URL, headers={"Host": API_HOST}, json=bad_body).status_code == 401
                assert anonymous.post(MCP_URL, headers={"Host": API_HOST, "Authorization": "Bearer invalid"}, json=bad_body).status_code == 401
            admin_calls = asyncio.run(call_as(admin_key, names))
            member_calls = asyncio.run(call_as(member_key, names, member=True))
            audits = checked(admin.get("/audit?per_page=50"), 200)
            assert isinstance(audits, list)
            relevant = [row for row in audits if row["api_key_id"] in {admin_key_id, member_key_id}]
            assert len(relevant) == len(admin_calls) + len(member_calls)
            assert all(row["outcome"] == "success" for row in relevant)
            assert {row["api_key_id"] for row in relevant} == {admin_key_id, member_key_id}
            assert all(row["user_id"] and row["server_id"] and row["original_tool_name"] for row in relevant)
            sensitive = [
                admin_password, member_password, admin_key, member_key,
                secret_value("bridgecart-mcp-bearer", "token"),
                secret_value("bridgecart-inventory-mcp-bearer", "token"),
                secret_value("bridgecart-shipping-mcp-bearer", "token"),
            ]
            for deployment in (
                "bridgecart-backend", "bridgecart-woocommerce-mcp",
                "bridgecart-inventory-mcp", "bridgecart-shipping-mcp",
            ):
                logs = kubectl("logs", "deployment/" + deployment, "--since=30m")
                if logs.returncode or any(value.encode() in logs.stdout for value in sensitive):
                    raise RuntimeError("Gateway or upstream credential log scan failed")
            print("External SDK client initialized, listed seven tools, and called WooCommerce, inventory, and shipping. Two-user audit attribution passed.")
            print("Backend and three upstream log scans found none of the tested credentials.")
        finally:
            if admin_key_id is not None:
                checked(admin.delete(f"/api-keys/{admin_key_id}", headers={"X-CSRF-Token": admin_csrf}), 204)
            if member_key_id is not None:
                checked(member.delete(f"/api-keys/{member_key_id}", headers={"X-CSRF-Token": member_csrf}), 204)


if __name__ == "__main__":
    main()
