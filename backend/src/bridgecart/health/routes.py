from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from bridgecart.health.service import database_is_ready

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    ready = await database_is_ready(
        request.app.state.engine,
        request.app.state.settings.database_connect_timeout,
    )
    if ready:
        return JSONResponse({"status": "ready", "database": "ready"})
    return JSONResponse(
        {"status": "not_ready", "database": "unavailable"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
