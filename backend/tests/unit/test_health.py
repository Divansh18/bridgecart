from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bridgecart.core.config import Settings
from bridgecart.main import create_app


@pytest.mark.asyncio
async def test_liveness_does_not_need_database() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://user:pass@127.0.0.1:1/db"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_reports_database_failure() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://user:pass@127.0.0.1:1/db"))
    with patch("bridgecart.health.routes.database_is_ready", new_callable=AsyncMock, return_value=False):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


@pytest.mark.asyncio
async def test_readiness_reports_database_success() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://user:pass@127.0.0.1:1/db"))
    with patch("bridgecart.health.routes.database_is_ready", new_callable=AsyncMock, return_value=True):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ready"
