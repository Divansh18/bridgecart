import httpx
import pytest

from bridgecart.core.config import Settings
from bridgecart.main import create_app


@pytest.mark.asyncio
async def test_readiness_fails_when_database_cannot_connect() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@127.0.0.1:1/db",
        database_connect_timeout=0.5,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
