"""Real PostgreSQL migration and HTTP access checks; opt in with TEST_DATABASE_URL."""

import asyncio
import os
import secrets
import subprocess
from datetime import timedelta
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from bridgecart.auth.bootstrap import provision
from bridgecart.auth.dependencies import authenticate_api_key
from bridgecart.auth.models import ApiKey, Invitation, LoginSession, User, utc_now
from bridgecart.auth.security import token_hash
from bridgecart.core.config import Settings
from bridgecart.main import create_app

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
async def database_url(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    supplied = os.getenv("BRIDGECART_TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Set BRIDGECART_TEST_DATABASE_URL to a PostgreSQL admin connection")
    root = make_url(supplied)
    name = "bridgecart_test_" + secrets.token_hex(5)
    admin_dsn = root.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    admin = await asyncpg.connect(dsn=admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        test_url = root.set(database=name).render_as_string(hide_password=False)
        environment = os.environ | {"BRIDGECART_DATABASE_URL": test_url}
        result = await asyncio.to_thread(
            subprocess.run,
            [str(BACKEND / ".venv/bin/alembic"), "upgrade", "head"],
            cwd=BACKEND,
            env=environment,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "Alembic upgrade failed"
        drift = await asyncio.to_thread(
            subprocess.run,
            [str(BACKEND / ".venv/bin/alembic"), "check"],
            cwd=BACKEND,
            env=environment,
            capture_output=True,
            check=False,
        )
        assert drift.returncode == 0, "Alembic metadata differs from migrated PostgreSQL schema"
        monkeypatch.setenv("BRIDGECART_DATABASE_URL", test_url)
        yield test_url
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


@pytest.mark.asyncio
async def test_team_access_against_migrated_postgres(
    database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    admin_password = "private admin password for test"
    member_password = "private member password for test"
    monkeypatch.setenv("BRIDGECART_INITIAL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("BRIDGECART_INITIAL_ADMIN_PASSWORD", admin_password)
    assert await provision() == "created"
    assert await provision() == "existing"
    settings = Settings(database_url=database_url)
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as admin:
        assert (await admin.get("/health/ready")).status_code == 200
        assert (await admin.get("/auth/me")).status_code == 401
        assert (
            await admin.post("/auth/login", json={"email": "admin@example.com", "password": "bad"})
        ).status_code == 401
        login = await admin.post("/auth/login", json={"email": "admin@example.com", "password": admin_password})
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        assert "samesite=lax" in login.headers["set-cookie"].lower()
        admin_csrf = admin.cookies["bridgecart_csrf"]
        assert (await admin.get("/auth/me")).json()["role"] == "admin"
        for _ in range(5):
            assert (
                await admin.post("/auth/login", json={"email": "unknown@example.com", "password": "wrong"})
            ).status_code == 401
        assert (
            await admin.post("/auth/login", json={"email": "unknown@example.com", "password": "wrong"})
        ).status_code == 429
        assert (await admin.post("/invitations", json={"email": "member@example.com"})).status_code == 403
        assert (
            await admin.post("/invitations", headers={"X-CSRF-Token": "wrong"}, json={"email": "member@example.com"})
        ).status_code == 403
        invite = await admin.post(
            "/invitations", headers={"X-CSRF-Token": admin_csrf}, json={"email": "member@example.com"}
        )
        assert invite.status_code == 201
        invitation_token = invite.json()["token"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as member:
            accepted = await member.post(
                "/auth/invitations/accept", json={"token": invitation_token, "password": member_password}
            )
            assert accepted.status_code == 201
            member_id = accepted.json()["id"]
            assert (
                await member.post(
                    "/auth/invitations/accept", json={"token": invitation_token, "password": member_password}
                )
            ).status_code == 400
            member_login = await member.post(
                "/auth/login", json={"email": "member@example.com", "password": member_password}
            )
            assert member_login.status_code == 200
            member_csrf = member.cookies["bridgecart_csrf"]
            assert (await member.get("/members")).status_code == 403
            assert (await member.get("/members/1/api-keys")).status_code == 403
            own_key_response = await member.post(
                "/api-keys", headers={"X-CSRF-Token": member_csrf}, json={"name": "test key"}
            )
            assert own_key_response.status_code == 201
            raw_key = own_key_response.json()["key"]
            key_id = own_key_response.json()["id"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer " + raw_key},
            ) as key_only:
                assert (await key_only.get("/auth/me")).status_code == 401
            own_list = (await member.get("/api-keys")).json()
            assert len(own_list) == 1 and "key" not in own_list[0]
            second_invite = await admin.post(
                "/invitations", headers={"X-CSRF-Token": admin_csrf}, json={"email": "second@example.com"}
            )
            assert second_invite.status_code == 201
            second_accepted = await member.post(
                "/auth/invitations/accept",
                json={"token": second_invite.json()["token"], "password": member_password},
            )
            assert second_accepted.status_code == 201
            second_key = await admin.post(
                f"/members/{second_accepted.json()['id']}/api-keys",
                headers={"X-CSRF-Token": admin_csrf},
                json={"name": "other member key"},
            )
            assert second_key.status_code == 201
            assert (
                await member.delete(f"/api-keys/{second_key.json()['id']}", headers={"X-CSRF-Token": member_csrf})
            ).status_code == 404
            assert len((await member.get("/api-keys")).json()) == 1
            async with app.state.session_factory() as db:
                assert (await authenticate_api_key("Bearer " + raw_key, db)).id == member_id
                with pytest.raises(HTTPException) as invalid:
                    await authenticate_api_key("Bearer invalid", db)
                assert invalid.value.status_code == 401
                with pytest.raises(HTTPException):
                    await authenticate_api_key("Bearer " + admin.cookies["bridgecart_session"], db)
                stored_user = await db.get(User, member_id)
                stored_admin = await db.get(User, 1)
                stored_key = await db.get(ApiKey, key_id)
                stored_invite = await db.scalar(select(Invitation).where(Invitation.email == "member@example.com"))
                assert stored_user and member_password not in stored_user.password_hash
                assert stored_admin and admin_password not in stored_admin.password_hash
                assert stored_key and raw_key not in stored_key.token_hash
                assert stored_invite and invitation_token not in stored_invite.token_hash
            assert (
                await member.delete(f"/api-keys/{key_id}", headers={"X-CSRF-Token": member_csrf})
            ).status_code == 204
            async with app.state.session_factory() as db:
                with pytest.raises(HTTPException) as revoked:
                    await authenticate_api_key("Bearer " + raw_key, db)
                assert revoked.value.status_code == 401
            issued = await admin.post(
                f"/members/{member_id}/api-keys",
                headers={"X-CSRF-Token": admin_csrf},
                json={"name": "admin issued"},
            )
            assert issued.status_code == 201
            admin_key = issued.json()["key"]
            assert "key" not in (await admin.get(f"/members/{member_id}/api-keys")).json()[-1]
            assert (
                await admin.delete(
                    f"/members/{member_id}/api-keys/{issued.json()['id']}",
                    headers={"X-CSRF-Token": admin_csrf},
                )
            ).status_code == 204
            async with app.state.session_factory() as db:
                with pytest.raises(HTTPException) as admin_revoked:
                    await authenticate_api_key("Bearer " + admin_key, db)
                assert admin_revoked.value.status_code == 401
            active_issued = await admin.post(
                f"/members/{member_id}/api-keys",
                headers={"X-CSRF-Token": admin_csrf},
                json={"name": "deactivation check"},
            )
            assert active_issued.status_code == 201
            active_key = active_issued.json()["key"]
            assert (await admin.get("/members")).status_code == 200
            assert (
                await admin.post(f"/members/{member_id}/deactivate", headers={"X-CSRF-Token": admin_csrf})
            ).status_code == 200
            assert (await member.get("/auth/me")).status_code == 401
            async with app.state.session_factory() as db:
                with pytest.raises(HTTPException) as inactive:
                    await authenticate_api_key("Bearer " + active_key, db)
                assert inactive.value.status_code == 401
            # Validation responses must not echo submitted secret fields.
            rejected = await member.post(
                "/auth/invitations/accept", json={"token": "private-invalid-token", "password": "short"}
            )
            assert rejected.status_code == 422 and "private-invalid-token" not in rejected.text
        # Logout and expiry use a distinct, still-active admin session.
        async with app.state.session_factory() as db:
            session = await db.scalar(select(LoginSession).join(User).where(User.email == "admin@example.com"))
            assert session and admin.cookies["bridgecart_session"] not in session.token_hash
            session.expires_at = utc_now() - timedelta(seconds=1)
            await db.commit()
        assert (await admin.get("/auth/me")).status_code == 401
        relogin = await admin.post("/auth/login", json={"email": "admin@example.com", "password": admin_password})
        assert relogin.status_code == 200
        assert (await admin.post("/auth/logout")).status_code == 403
        assert (
            await admin.post("/auth/logout", headers={"X-CSRF-Token": admin.cookies["bridgecart_csrf"]})
        ).status_code == 200
        assert (await admin.get("/auth/me")).status_code == 401
        expired_token = "expired-token-long-enough-to-validate"
        async with app.state.session_factory() as db:
            expired = Invitation(
                email="expired@example.com",
                token_hash=token_hash("invitation", expired_token),
                created_by=1,
                expires_at=utc_now() - timedelta(seconds=1),
            )
            db.add(expired)
            await db.commit()
        # Direct hash match with an expired invitation is rejected without creating a user.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as anonymous:
            expired_result = await anonymous.post(
                "/auth/invitations/accept", json={"token": expired_token, "password": member_password}
            )
            assert expired_result.status_code == 400
        async with app.state.session_factory() as db:
            revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "20261011_01"
    await app.state.engine.dispose()
    output = capsys.readouterr()
    for secret in (admin_password, member_password, invitation_token, raw_key, admin_key, active_key):
        assert secret not in output.out and secret not in output.err
