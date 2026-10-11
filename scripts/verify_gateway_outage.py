"""Temporarily stop only shipping, prove failure isolation, and restore it."""

import asyncio
import json
import secrets
import subprocess
import time

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from verify_backend_live import checked, client, kubectl, login, secret_value
from verify_gateway_live import API_HOST, MCP_URL, wait_status

DEPLOYMENT = "bridgecart-shipping-mcp"


def command(*args: str) -> subprocess.CompletedProcess[bytes]:
    return kubectl(*args)


async def call_healthy(key: str, names: dict[str, str]) -> None:
    async with httpx2.AsyncClient(
        headers={"Host": API_HOST, "Authorization": "Bearer " + key},
        timeout=httpx2.Timeout(15, connect=3),
        trust_env=False,
    ) as http:
        async with streamable_http_client(MCP_URL, http_client=http, terminate_on_close=False) as streams:
            async with ClientSession(*streams, read_timeout_seconds=15) as session:
                await session.initialize()
                listed = {tool.name for tool in (await session.list_tools()).tools}
                assert names["list_products"] in listed
                assert names["lookup_inventory"] in listed
                assert names["estimate_shipping"] not in listed
                products = await session.call_tool(names["list_products"], {"per_page": 1})
                stock = await session.call_tool(names["lookup_inventory"], {"sku": "BRIDGECART-DEMO-001"})
                assert not products.is_error and not stock.is_error


def main() -> None:
    admin_email = secret_value("bridgecart-initial-admin", "admin-email")
    admin_password = secret_value("bridgecart-initial-admin", "admin-password")
    observed = command("get", "deployment", DEPLOYMENT, "-o", "json")
    if observed.returncode:
        raise RuntimeError("Cannot inspect shipping Deployment")
    deployment = json.loads(observed.stdout)
    labels = deployment["metadata"]["labels"]
    if labels.get("app.kubernetes.io/instance") != "bridgecart" or deployment["spec"]["replicas"] != 1:
        raise RuntimeError("Shipping Deployment ownership or replica check failed")
    with client() as admin:
        csrf = login(admin, admin_email, admin_password)
        catalog = checked(admin.get("/servers"), 200)
        assert isinstance(catalog, list)
        names = {tool["original_name"]: tool["name"] for row in catalog for tool in row["tools"]}
        shipping = next(row for row in catalog if row["name"] == "Demo Shipping")
        issued = checked(admin.post(
            "/api-keys", headers={"X-CSRF-Token": csrf},
            json={"name": "milestone4b-outage-" + secrets.token_hex(3)},
        ), 201)
        key_id, key = issued["id"], str(issued["key"])
        stopped = False
        try:
            result = command("scale", "deployment", DEPLOYMENT, "--replicas=0")
            if result.returncode:
                raise RuntimeError("Could not stop shipping for controlled outage")
            stopped = True
            result = command("rollout", "status", "deployment/" + DEPLOYMENT, "--timeout=90s")
            if result.returncode:
                raise RuntimeError("Shipping did not stop")
            time.sleep(16)  # Let the bounded discovery cache expire.
            wait_status(admin, shipping["id"], "Unreachable", 30)
            asyncio.run(call_healthy(key, names))
            print("Shipping became Unreachable; WooCommerce and inventory remained callable through the external gateway.")
        finally:
            if stopped:
                restored = command("scale", "deployment", DEPLOYMENT, "--replicas=1")
                if restored.returncode:
                    raise RuntimeError("Shipping restore failed; inspect the Deployment immediately")
                ready = command("rollout", "status", "deployment/" + DEPLOYMENT, "--timeout=180s")
                if ready.returncode:
                    raise RuntimeError("Shipping did not become ready after restoration")
                time.sleep(16)
                wait_status(admin, shipping["id"], "Connected", 30)
                print("Shipping restored and Connected.")
            checked(admin.delete(f"/api-keys/{key_id}", headers={"X-CSRF-Token": csrf}), 204)


if __name__ == "__main__":
    main()
