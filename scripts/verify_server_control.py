"""Reversible live Shipping controls, failure isolation, UI, and audit checks."""

import asyncio
import json
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from verify_backend_live import (
    MEMBER_EMAIL,
    MEMBER_SECRET,
    checked,
    client,
    kubectl,
    login,
    secret_value,
)
from verify_gateway_live import wait_status

DEPLOYMENT = "bridgecart-shipping-mcp"
GATEWAY_URL = "http://127.0.0.1:8088/mcp"
GATEWAY_HOST = "api.bridgecart.local"


def command(*args: str) -> bytes:
    result = kubectl(*args)
    if result.returncode:
        raise RuntimeError("Shipping Kubernetes command failed: " + " ".join(args[:3]))
    return result.stdout


def shipping_pod() -> tuple[str, str]:
    pods = json.loads(
        command(
            "get",
            "pods",
            "-l",
            "app.kubernetes.io/component=shipping-mcp",
            "-o",
            "json",
        )
    )["items"]
    if len(pods) != 1:
        raise RuntimeError("Expected exactly one owned Shipping pod")
    pod = pods[0]
    if pod["metadata"]["labels"].get("app.kubernetes.io/instance") != "bridgecart":
        raise RuntimeError("Shipping pod ownership check failed")
    return pod["metadata"]["name"], pod["metadata"]["uid"]


def result_text(result: Any) -> str:
    return " ".join(str(getattr(block, "text", "")) for block in result.content)


async def mcp_check(
    key: str,
    names: dict[str, str],
    *,
    shipping_present: bool | None,
    shipping_error: str | None = None,
) -> tuple[float | None, str | None]:
    async with (
        httpx2.AsyncClient(
            headers={"Host": GATEWAY_HOST, "Authorization": "Bearer " + key},
            timeout=httpx2.Timeout(15, connect=3),
            trust_env=False,
        ) as http,
        streamable_http_client(
            GATEWAY_URL, http_client=http, terminate_on_close=False
        ) as streams,
        ClientSession(*streams, read_timeout_seconds=15) as session,
    ):
        await session.initialize()
        tools = {tool.name for tool in (await session.list_tools()).tools}
        assert names["list_products"] in tools and names["lookup_inventory"] in tools
        if shipping_present is not None:
            assert (names["estimate_shipping"] in tools) is shipping_present
        products = await session.call_tool(names["list_products"], {"per_page": 1})
        inventory = await session.call_tool(
            names["lookup_inventory"], {"sku": "BRIDGECART-DEMO-001"}
        )
        assert not products.is_error and not inventory.is_error
        if shipping_present is None:
            return None, None
        started = time.monotonic()
        shipping = await session.call_tool(
            names["estimate_shipping"],
            {"pin_code": "560001", "weight_kg": "1.00", "service_level": "standard"},
        )
        duration = time.monotonic() - started
        detail = result_text(shipping)
        if shipping_error is None:
            assert not shipping.is_error
            assert shipping.structured_content["amount"] == "80.00"
            return None, None
        assert shipping.is_error and shipping_error.lower() in detail.lower()
        assert duration < 13, f"Shipping failure exceeded call timeout: {duration:.2f}s"
        return duration, detail


async def cached_disable_check(
    key: str, names: dict[str, str], admin: Any, csrf: str, server_id: str
) -> str:
    async with (
        httpx2.AsyncClient(
            headers={"Host": GATEWAY_HOST, "Authorization": "Bearer " + key},
            timeout=httpx2.Timeout(15, connect=3),
            trust_env=False,
        ) as http,
        streamable_http_client(
            GATEWAY_URL, http_client=http, terminate_on_close=False
        ) as streams,
        ClientSession(*streams, read_timeout_seconds=15) as session,
    ):
        await session.initialize()
        before = {tool.name for tool in (await session.list_tools()).tools}
        assert len(before) == 7 and names["estimate_shipping"] in before
        checked(
            admin.patch(
                f"/servers/{server_id}",
                headers={"X-CSRF-Token": csrf},
                json={"enabled": False},
            ),
            200,
        )
        after = {tool.name for tool in (await session.list_tools()).tools}
        assert len(after) == 6 and names["estimate_shipping"] not in after
        denied = await session.call_tool(
            names["estimate_shipping"], {"pin_code": "560001", "weight_kg": "1.00"}
        )
        assert denied.is_error and "disabled" in result_text(denied).lower()
        assert names["list_products"] in after and names["lookup_inventory"] in after
        return result_text(denied)


def browser_check(
    mode: str, admin_email: str, admin_password: str, member_password: str
) -> dict[str, str]:
    payload = {
        "mode": mode,
        "admin_email": admin_email,
        "admin_password": admin_password,
        "member_email": MEMBER_EMAIL,
        "member_password": member_password,
    }
    completed = subprocess.run(
        ["python3", str(Path(__file__).with_name("server_control_browser.py"))],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    output = completed.stdout + completed.stderr
    if any(secret in output for secret in (admin_password, member_password)):
        raise RuntimeError("Browser output contained a credential; output suppressed")
    if completed.returncode:
        raise RuntimeError("Browser check failed: " + completed.stderr[-700:])
    return json.loads(completed.stdout)


def main() -> None:
    admin_email = secret_value("bridgecart-initial-admin", "admin-email")
    admin_password = secret_value("bridgecart-initial-admin", "admin-password")
    member_password = secret_value(MEMBER_SECRET, "member-password")
    deploy = json.loads(command("get", "deployment", DEPLOYMENT, "-o", "json"))
    original_replicas = deploy["spec"]["replicas"]
    if (
        deploy["metadata"]["labels"].get("app.kubernetes.io/instance") != "bridgecart"
        or original_replicas != 1
    ):
        raise RuntimeError(
            "Shipping Deployment ownership or replica count is unexpected"
        )
    with client() as admin, client() as member:
        admin_csrf = login(admin, admin_email, admin_password)
        member_csrf = login(member, MEMBER_EMAIL, member_password)
        users = checked(admin.get("/members"), 200)
        user = next(row for row in users if row["email"] == MEMBER_EMAIL)
        assert user["active"] and user["role"] == "member"
        catalog = checked(admin.get("/servers"), 200)
        assert len(catalog) == 3 and all(
            row["status"] == "Connected" for row in catalog
        )
        shipping = next(row for row in catalog if row["name"] == "Demo Shipping")
        names = {
            tool["original_name"]: tool["name"]
            for row in catalog
            for tool in row["tools"]
        }
        assert len(names) == 7 and shipping["enabled"]
        issued = checked(
            member.post(
                "/api-keys",
                headers={"X-CSRF-Token": member_csrf},
                json={"name": "final-server-control-" + secrets.token_hex(4)},
            ),
            201,
        )
        key_id, key = int(issued["id"]), str(issued["key"])
        disabled = False
        scaled = False
        try:
            disabled = True
            asyncio.run(
                cached_disable_check(key, names, admin, admin_csrf, shipping["id"])
            )
            wait_status(admin, shipping["id"], "Disabled")
            asyncio.run(
                mcp_check(key, names, shipping_present=False, shipping_error="disabled")
            )
            chat = browser_check(
                "disabled-chat", admin_email, admin_password, member_password
            )
            correlation = chat["correlation_id"]
            print(
                "Disabled: external tool refresh hid Shipping; cached call rejected; dashboard chat used Inventory without Shipping."
            )
            checked(
                admin.patch(
                    f"/servers/{shipping['id']}",
                    headers={"X-CSRF-Token": admin_csrf},
                    json={"enabled": True},
                ),
                200,
            )
            disabled = False
            wait_status(admin, shipping["id"], "Connected")
            asyncio.run(mcp_check(key, names, shipping_present=True))
            print(
                "Enabled: Shipping tool returned; WooCommerce and Inventory remained callable."
            )

            old_name, old_uid = shipping_pod()
            command("delete", "pod", old_name, "--wait=false")
            asyncio.run(mcp_check(key, names, shipping_present=None))
            command("wait", "--for=delete", "pod/" + old_name, "--timeout=180s")
            command("rollout", "status", "deployment/" + DEPLOYMENT, "--timeout=180s")
            new_name, new_uid = shipping_pod()
            assert new_uid != old_uid
            print(
                "Pod replacement: owned Shipping pod UID changed; healthy upstream calls succeeded during replacement."
            )

            command("scale", "deployment", DEPLOYMENT, "--replicas=0")
            scaled = True
            command("wait", "--for=delete", "pod/" + new_name, "--timeout=180s")
            time.sleep(16)
            wait_status(admin, shipping["id"], "Unreachable", 35)
            browser_check("unreachable", admin_email, admin_password, member_password)
            elapsed, outage_detail = asyncio.run(
                mcp_check(
                    key, names, shipping_present=False, shipping_error="unavailable"
                )
            )
            print(
                f"Sustained outage: dashboard showed Unreachable; Shipping failed in {elapsed:.2f}s: {outage_detail}"
            )
        finally:
            try:
                if scaled:
                    command(
                        "scale",
                        "deployment",
                        DEPLOYMENT,
                        f"--replicas={original_replicas}",
                    )
                    command(
                        "rollout",
                        "status",
                        "deployment/" + DEPLOYMENT,
                        "--timeout=180s",
                    )
            finally:
                try:
                    if disabled:
                        checked(
                            admin.patch(
                                f"/servers/{shipping['id']}",
                                headers={"X-CSRF-Token": admin_csrf},
                                json={"enabled": True},
                            ),
                            200,
                        )
                finally:
                    checked(
                        member.delete(
                            f"/api-keys/{key_id}", headers={"X-CSRF-Token": member_csrf}
                        ),
                        204,
                    )
        time.sleep(16)
        wait_status(admin, shipping["id"], "Connected", 35)
        all_servers = checked(admin.get("/servers"), 200)
        assert all(row["status"] == "Connected" for row in all_servers)
        audits = checked(admin.get(f"/audit?user_id={user['id']}&per_page=100"), 200)
        relevant = [row for row in audits if row["api_key_id"] == key_id]
        assert any(
            row["error_category"] == "disabled" and row["outcome"] == "rejected"
            for row in relevant
        )
        assert any(
            row["error_category"] == "upstream_unavailable"
            and row["outcome"] == "upstream_error"
            for row in relevant
        )
        assert any(
            row["outcome"] == "success"
            and row["original_tool_name"] == "lookup_inventory"
            for row in relevant
        )
        assert not any(
            row["original_tool_name"] in {"create_product", "update_order_status"}
            for row in relevant
        )
        chat_rows = [row for row in audits if row["correlation_id"] == correlation]
        assert chat_rows and all(row["user_id"] == user["id"] for row in chat_rows)
        assert all(row["server_name"] != "Demo Shipping" for row in chat_rows)
        assert not any(
            row["original_tool_name"] in {"create_product", "update_order_status"}
            for row in chat_rows
        )
        deployments = json.loads(command("get", "deployments", "-o", "json"))["items"]
        required = {
            "bridgecart-backend",
            "bridgecart-frontend",
            "bridgecart-wordpress",
            "bridgecart-woocommerce-mcp",
            "bridgecart-inventory-mcp",
            DEPLOYMENT,
        }
        assert required <= {row["metadata"]["name"] for row in deployments}
        assert all(
            row["status"].get("readyReplicas", 0) == row["spec"]["replicas"]
            for row in deployments
            if row["metadata"]["name"] in required
        )
        statefulsets = json.loads(command("get", "statefulsets", "-o", "json"))["items"]
        assert all(
            row["status"].get("readyReplicas", 0) == row["spec"]["replicas"]
            for row in statefulsets
        )
        pvcs = json.loads(command("get", "pvc", "-o", "json"))["items"]
        assert len(pvcs) == 3 and all(row["status"]["phase"] == "Bound" for row in pvcs)
        print(
            f"Restored: all three Connected, workloads Ready, three PVCs Bound; user B key #{key_id} revoked; {len(relevant)} key-audited calls; {len(chat_rows)} member chat-audited calls."
        )


if __name__ == "__main__":
    main()
