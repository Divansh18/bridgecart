"""Read-only Codex CLI acceptance against the local gateway as an existing member.

The temporary raw key lives only in this process and the Codex child environment.
Never print captured CLI output before checking it for the credential.
"""

import asyncio
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from collections.abc import Callable
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

GATEWAY_URL = "http://api.bridgecart.local:8088/mcp"
TEST_TOOLS = {"list_orders", "lookup_inventory", "estimate_shipping"}


def run_codex(key: str, prompt: str, workdir: Path) -> tuple[str, list[dict[str, Any]]]:
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Codex CLI is unavailable")
    environment = os.environ.copy()
    environment["BRIDGECART_ACCEPTANCE_KEY"] = key
    environment["NO_PROXY"] = "api.bridgecart.local,127.0.0.1,localhost"
    environment["no_proxy"] = environment["NO_PROXY"]
    completed = subprocess.run(
        [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            str(workdir),
            "-m",
            "gpt-6-luna",
            "-c",
            f'mcp_servers.bridgecart.url="{GATEWAY_URL}"',
            "-c",
            'mcp_servers.bridgecart.bearer_token_env_var="BRIDGECART_ACCEPTANCE_KEY"',
            prompt,
        ],
        env=environment,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    if key in combined:
        raise RuntimeError("Codex output contained a credential; output suppressed")
    events: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if completed.returncode:
        safe_errors = [
            str(event.get("message", ""))[:300]
            for event in events
            if event.get("type") == "error"
        ]
        raise RuntimeError(
            f"Codex CLI exited {completed.returncode}: {safe_errors or 'no structured error'}"
        )
    answers = [
        str(event["item"].get("text", ""))
        for event in events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "agent_message"
    ]
    if not answers:
        raise RuntimeError("Codex CLI returned no final answer")
    return answers[-1], events


def call_names(events: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "mcp_tool_call":
            names.add(str(item.get("tool", "")))
    return names


async def check_revocation(key: str, revoke: Callable[[], None]) -> None:
    # Keep this MCP session open across revocation. The Codex prompts above
    # provide separate evidence of natural-language LLM tool use.
    async with (
        httpx2.AsyncClient(
            headers={"Host": "api.bridgecart.local", "Authorization": "Bearer " + key},
            timeout=httpx2.Timeout(15, connect=3),
            trust_env=False,
        ) as http,
        streamable_http_client(
            "http://127.0.0.1:8088/mcp", http_client=http, terminate_on_close=False
        ) as streams,
        ClientSession(*streams, read_timeout_seconds=15) as session,
    ):
        await session.initialize()
        await session.list_tools()
        revoke()
        response = await http.get("http://127.0.0.1:8088/mcp")
        if response.status_code != 401:
            raise RuntimeError("Revoked key did not return HTTP 401")
        try:
            await session.list_tools()
        except Exception:  # noqa: BLE001 - SDK may wrap closed transport in a task group.
            return
        raise RuntimeError("Revoked key was accepted on an existing MCP session")


def main() -> None:
    admin_email = secret_value("bridgecart-initial-admin", "admin-email")
    admin_password = secret_value("bridgecart-initial-admin", "admin-password")
    member_password = secret_value(MEMBER_SECRET, "member-password")
    with client() as admin, client() as member:
        login(admin, admin_email, admin_password)
        member_csrf = login(member, MEMBER_EMAIL, member_password)
        members = checked(admin.get("/members"), 200)
        assert isinstance(members, list)
        user = next((row for row in members if row["email"] == MEMBER_EMAIL), None)
        if user is None or not user["active"] or user["role"] != "member":
            raise RuntimeError("User B must be an active member")
        user_id = int(user["id"])
        servers = checked(admin.get("/servers"), 200)
        assert isinstance(servers, list)
        if len(servers) != 3 or any(row["status"] != "Connected" for row in servers):
            raise RuntimeError("All three upstreams must be Connected")
        exposed = {
            tool["original_name"]: tool["name"]
            for server in servers
            for tool in server["tools"]
        }
        if len(exposed) != 7 or not TEST_TOOLS <= exposed.keys():
            raise RuntimeError("Expected seven tools across three upstreams")
        created = checked(
            member.post(
                "/api-keys",
                headers={"X-CSRF-Token": member_csrf},
                json={"name": "final-external-client-" + secrets.token_hex(4)},
            ),
            201,
        )
        key_id, key = int(created["id"]), str(created["key"])
        revoked = False

        def revoke() -> None:
            nonlocal revoked
            if not revoked:
                checked(
                    member.delete(
                        f"/api-keys/{key_id}", headers={"X-CSRF-Token": member_csrf}
                    ),
                    204,
                )
                revoked = True

        try:
            with tempfile.TemporaryDirectory(
                prefix="bridgecart-external-client-"
            ) as directory:
                workdir = Path(directory)
                discovery, _ = run_codex(
                    key,
                    "Use only the BridgeCart MCP gateway. List the names of all available "
                    "BridgeCart tools and group them by WooCommerce, demo inventory, and "
                    "demo shipping. Do not call any write tool or use shell/network tools.",
                    workdir,
                )
                if not all(
                    server in discovery.lower()
                    for server in ("woocommerce", "inventory", "shipping")
                ):
                    raise RuntimeError("Codex did not report all three upstreams")
                orders, order_events = run_codex(
                    key,
                    "Use only the BridgeCart MCP gateway list_orders tool with today=true "
                    "to answer which orders were placed today in Asia/Kolkata. State the "
                    "local calendar date and order IDs (or none). Read only; do not use shell "
                    "or network tools and do not change products or orders.",
                    workdir,
                )
                workflow, workflow_events = run_codex(
                    key,
                    "Using only BridgeCart MCP tools, check seeded demo inventory for exact "
                    "SKU BRIDGECART-DEMO-001 and estimate standard demo shipping for "
                    "1.00 kg to Bengaluru PIN 560001. Use both inventory and shipping "
                    "tools in this one response. Clearly identify both results as demo "
                    "data. Read only; do not use shell/network tools or change store data.",
                    workdir,
                )
            if exposed["list_orders"] not in call_names(order_events):
                raise RuntimeError("Codex did not call list_orders for today's orders")
            workflow_calls = call_names(workflow_events)
            if (
                not {exposed["lookup_inventory"], exposed["estimate_shipping"]}
                <= workflow_calls
            ):
                raise RuntimeError("One Codex prompt did not call both demo upstreams")
            if "demo" not in workflow.lower():
                raise RuntimeError("Codex did not label demo results")
            audits = checked(admin.get(f"/audit?user_id={user_id}&per_page=100"), 200)
            assert isinstance(audits, list)
            relevant = [row for row in audits if row["api_key_id"] == key_id]
            found = {row["original_tool_name"] for row in relevant}
            if not TEST_TOOLS <= found or any(
                row["user_id"] != user_id for row in relevant
            ):
                raise RuntimeError("Audit attribution or required tool calls missing")
            if found & {"create_product", "update_order_status"}:
                raise RuntimeError("External client attempted a store mutation")
            if any(row["outcome"] != "success" for row in relevant):
                raise RuntimeError("At least one external-client tool call failed")
            logs = kubectl("logs", "deployment/bridgecart-backend", "--since=30m")
            if logs.returncode or key.encode() in logs.stdout:
                raise RuntimeError("Backend log credential scan failed")
            asyncio.run(check_revocation(key, revoke))
            print(
                f"User B: {MEMBER_EMAIL} (ID {user_id}); test key ID {key_id}: revoked"
            )
            print(
                "Gateway catalog: seven tools; Codex CLI reported all three upstreams"
            )
            print("Codex CLI: list_orders(today=true) called; answer: " + orders[:600])
            print(
                "Codex CLI: one prompt called inventory and shipping; answer: "
                + workflow[:600]
            )
            print(
                f"Audit: {len(relevant)} successful calls attributed to user B and test key"
            )
            print("Open SDK connection rejected the first request after key revocation")
            print("Backend log scan: temporary key absent")
        finally:
            revoke()


if __name__ == "__main__":
    main()
