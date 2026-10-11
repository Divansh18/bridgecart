"""Gateway security and audit behavior against an isolated migrated PostgreSQL DB."""

import asyncio
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import httpx2
import pytest
from cryptography.fernet import Fernet
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent, Tool
from sqlalchemy import select
from sqlalchemy.engine import make_url

from bridgecart.auth.dependencies import authenticate_api_key_actor
from bridgecart.auth.models import ApiKey, User, utc_now
from bridgecart.auth.security import hash_password, token_hash
from bridgecart.core.config import Settings, get_settings
from bridgecart.gateway.bootstrap import bootstrap
from bridgecart.gateway.models import ToolAudit, UpstreamServer
from bridgecart.gateway.security import cipher, validate_header, validate_url
from bridgecart.gateway.service import Gateway, GatewayFailure, exposed_name
from bridgecart.main import create_app

BACKEND = Path(__file__).resolve().parents[2]
URLS = (
    "http://bridgecart-woocommerce-mcp:8001/mcp",
    "http://bridgecart-inventory-mcp:8002/mcp",
    "http://bridgecart-shipping-mcp:8003/mcp",
)


@pytest.fixture
async def database_url(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    supplied = os.getenv("BRIDGECART_TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Set BRIDGECART_TEST_DATABASE_URL to a PostgreSQL admin connection")
    root = make_url(supplied)
    name = "bridgecart_gateway_test_" + secrets.token_hex(5)
    admin = await asyncpg.connect(
        dsn=root.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    )
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        test_url = root.set(database=name).render_as_string(hide_password=False)
        result = await asyncio.to_thread(
            subprocess.run,
            [str(BACKEND / ".venv/bin/alembic"), "upgrade", "head"],
            cwd=BACKEND,
            env=os.environ | {"BRIDGECART_DATABASE_URL": test_url},
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "Alembic upgrade failed"
        monkeypatch.setenv("BRIDGECART_DATABASE_URL", test_url)
        yield test_url
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


@pytest.mark.asyncio
async def test_registry_routing_cache_audit_and_transport_revocation(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    encryption_key = Fernet.generate_key().decode()
    settings = Settings(
        database_url=database_url,
        gateway_enabled=True,
        upstream_encryption_key=encryption_key,
        gateway_allowed_urls=",".join(URLS),
    )
    app = create_app(settings)
    gateway = app.state.gateway
    admin_password = "private gateway admin test password"
    member_password = "private gateway member test password"
    raw_admin_key = "bck_" + secrets.token_urlsafe(30)
    raw_member_key = "bck_" + secrets.token_urlsafe(30)
    async with app.state.session_factory() as db:
        admin = User(email="admin@example.com", password_hash=hash_password(admin_password), role="admin", active=True)
        member = User(
            email="member@example.com", password_hash=hash_password(member_password), role="member", active=True
        )
        db.add_all([admin, member])
        await db.flush()
        admin_key = ApiKey(
            user_id=admin.id,
            created_by=admin.id,
            name="admin",
            prefix="bck_",
            token_hash=token_hash("api-key", raw_admin_key),
            created_at=utc_now(),
        )
        member_key = ApiKey(
            user_id=member.id,
            created_by=admin.id,
            name="member",
            prefix="bck_",
            token_hash=token_hash("api-key", raw_member_key),
            created_at=utc_now(),
        )
        db.add_all([admin_key, member_key])
        await db.commit()

    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_connect(
        server: UpstreamServer, operation: str, name: str = "", args: dict[str, Any] | None = None
    ) -> Any:
        calls.append((server.id, operation, args or {}))
        assert gateway._headers(server) == {"Authorization": "Bearer upstream-private"}
        if operation == "discover":
            return [Tool(name="lookup", description="demo", inputSchema={"type": "object", "properties": {}})]
        if args and args.get("fail") == "timeout":
            raise GatewayFailure("timeout", "Upstream timed out; a write may have completed")
        if args and args.get("fail") == "tool":
            return CallToolResult(content=[TextContent(type="text", text="private upstream error")], is_error=True)
        return CallToolResult(content=[TextContent(type="text", text="ok")], structured_content={"from": server.name})

    monkeypatch.setattr(gateway, "_connect", fake_connect)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as admin_http:
        login = await admin_http.post("/auth/login", json={"email": "admin@example.com", "password": admin_password})
        assert login.status_code == 200
        csrf = admin_http.cookies["bridgecart_csrf"]
        created = await admin_http.post(
            "/servers",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Woo", "url": URLS[0], "auth_type": "bearer", "credential": "upstream-private"},
        )
        assert created.status_code == 201
        assert "upstream-private" not in created.text
        first = created.json()["id"]
        second_result = await admin_http.post(
            "/servers",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Inventory", "url": URLS[1], "auth_type": "bearer", "credential": "upstream-private"},
        )
        assert second_result.status_code == 201
        second = second_result.json()["id"]
        server_list = await admin_http.get("/servers")
        assert server_list.status_code == 200
        assert "upstream-private" not in server_list.text
        assert len(server_list.json()) == 2
        assert all(row["status"] == "Connected" for row in server_list.json())
        assert len(await gateway.list_tools()) == 2
        assert sum(operation == "discover" for _, operation, _ in calls) == 2  # cached
        public_first = exposed_name(first, "lookup")
        public_second = exposed_name(second, "lookup")
        assert public_first != public_second
        async with app.state.session_factory() as db:
            stored = await db.get(UpstreamServer, first)
            assert stored is not None
            assert b"upstream-private" not in stored.credential_encrypted
            assert cipher(settings).decrypt(stored.credential_encrypted) == b"upstream-private"
            admin_actor = await authenticate_api_key_actor("Bearer " + raw_admin_key, db)
            member_actor = await authenticate_api_key_actor("Bearer " + raw_member_key, db)
        a, b = await asyncio.gather(
            gateway.execute(admin_actor, public_first, {}),
            gateway.execute(member_actor, public_second, {}),
        )
        assert a.structured_content == {"from": "Woo"}
        assert b.structured_content == {"from": "Inventory"}
        await gateway.execute(admin_actor, public_first, {"fail": "timeout"})
        await gateway.execute(member_actor, public_second, {"fail": "tool"})
        disabled = await admin_http.patch(f"/servers/{first}", headers={"X-CSRF-Token": csrf}, json={"enabled": False})
        assert disabled.status_code == 200
        denied = await gateway.execute(admin_actor, public_first, {})
        assert denied.is_error
        assert [tool.name for tool in await gateway.list_tools()] == [public_second]
        await admin_http.delete(f"/servers/{second}", headers={"X-CSRF-Token": csrf})
        assert await gateway.list_tools() == []
        audit_response = await admin_http.get("/audit?per_page=10")
        assert audit_response.status_code == 200
        assert len(audit_response.json()) == 5
        assert {row["outcome"] for row in audit_response.json()} == {"success", "timeout", "upstream_error", "rejected"}
        assert {row["user_id"] for row in audit_response.json()} == {admin_actor.user.id, member_actor.user.id}
        assert all("upstream-private" not in str(row) for row in audit_response.json())

    # SDK client retains its transport; a revoked key must fail on the next POST.
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + raw_member_key}
        ) as http:
            async with streamable_http_client("http://test/mcp", http_client=http, terminate_on_close=False) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    assert (await client.list_tools()).tools == []
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as admin_again:
                        assert (
                            await admin_again.post(
                                "/auth/login", json={"email": "admin@example.com", "password": admin_password}
                            )
                        ).status_code == 200
                        token = admin_again.cookies["bridgecart_csrf"]
                        third_result = await admin_again.post(
                            "/servers",
                            headers={"X-CSRF-Token": token},
                            json={
                                "name": "Shipping",
                                "url": URLS[2],
                                "auth_type": "bearer",
                                "credential": "upstream-private",
                            },
                        )
                        assert third_result.status_code == 201
                        third = third_result.json()["id"]
                        refreshed = await client.list_tools()
                        assert len(refreshed.tools) == 1
                        public_third = refreshed.tools[0].name
                        assert public_third == exposed_name(third, "lookup")
                        assert (
                            await admin_again.patch(
                                f"/servers/{third}", headers={"X-CSRF-Token": token}, json={"enabled": False}
                            )
                        ).status_code == 200
                        assert (await client.list_tools()).tools == []  # explicit refresh on the same SDK session
                        assert (await client.call_tool(public_third, {})).is_error  # cached direct call denied
                    async with app.state.session_factory() as db:
                        key = await db.scalar(
                            select(ApiKey).where(ApiKey.token_hash == token_hash("api-key", raw_member_key))
                        )
                        assert key is not None
                        key.revoked_at = utc_now()
                        await db.commit()
                    with pytest.raises(MCPError):
                        await client.list_tools()
                    assert (await gateway.execute(member_actor, public_third, {})).is_error

    async with app.state.session_factory() as db:
        retained = (await db.scalars(select(ToolAudit).where(ToolAudit.api_key_id == member_key.id))).all()
        assert retained and all(row.user_email == "member@example.com" for row in retained)
        assert any(row.server_name == "Inventory" for row in retained)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as member_http:
        assert (
            await member_http.post("/auth/login", json={"email": "member@example.com", "password": member_password})
        ).status_code == 200
        assert (await member_http.get("/servers")).status_code == 403
        assert (await member_http.get("/audit?user_id=1")).status_code == 403
        own = await member_http.get("/audit")
        assert own.status_code == 200
        assert all(row["user_id"] == member_actor.user.id for row in own.json())
    await app.state.engine.dispose()


def test_registry_destination_and_header_policy() -> None:
    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db", gateway_allowed_urls=",".join(URLS))
    assert validate_url(URLS[0], settings) == URLS[0]
    from fastapi import HTTPException

    for url in (
        "http://169.254.169.254:80/mcp",
        "http://localhost:8001/mcp",
        "http://user@bridgecart-woocommerce-mcp:8001/mcp",
        "http://bridgecart-woocommerce-mcp:8001/else",
        "http://evil.example:8001/mcp",
    ):
        with pytest.raises(HTTPException):
            validate_url(url, settings)
    for header in ("Host", "Connection", "X-Forwarded-For", "X-Bad\r\nInjected", "Authorization"):
        with pytest.raises(HTTPException):
            validate_header(header)
    secured = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        gateway_enabled=True,
        upstream_encryption_key=Fernet.generate_key().decode(),
        gateway_allowed_urls=",".join(URLS),
    )
    upstream = UpstreamServer(
        id="00000000-0000-0000-0000-000000000001",
        name="Header demo",
        url=URLS[0],
        enabled=True,
        auth_type="header",
        header_name="X-Demo-Token",
        credential_encrypted=cipher(secured).encrypt(b"upstream-only"),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    assert Gateway(secured, None)._headers(upstream) == {"X-Demo-Token": "upstream-only"}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_seed_is_repeatable_without_overwriting_admin_changes(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRIDGECART_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("BRIDGECART_GATEWAY_ALLOWED_URLS", ",".join(URLS))
    monkeypatch.setenv("BRIDGECART_UPSTREAM_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for name in ("WOOCOMMERCE", "INVENTORY", "SHIPPING"):
        monkeypatch.setenv("BRIDGECART_SEED_" + name + "_TOKEN", secrets.token_urlsafe(32))
    get_settings.cache_clear()
    try:
        await bootstrap()
        await bootstrap()
        app = create_app(get_settings())
        async with app.state.session_factory() as db:
            rows = (await db.scalars(select(UpstreamServer))).all()
            assert len(rows) == 3
            woo = next(row for row in rows if row.name == "WooCommerce")
            woo.name = "Admin edited Woo"
            woo.enabled = False
            await db.commit()
        await bootstrap()
        async with app.state.session_factory() as db:
            rows = (await db.scalars(select(UpstreamServer))).all()
            assert len(rows) == 3
            woo = await db.get(UpstreamServer, woo.id)
            assert woo is not None and woo.name == "Admin edited Woo" and not woo.enabled
        await app.state.engine.dispose()
    finally:
        get_settings.cache_clear()
