from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bridgecart.api_keys.routes import router as api_keys_router
from bridgecart.auth.rate_limit import LoginLimiter
from bridgecart.auth.routes import router as auth_router
from bridgecart.core.config import Settings, get_settings
from bridgecart.core.logging import configure_logging
from bridgecart.db.session import create_session_factory
from bridgecart.health.routes import router as health_router
from bridgecart.members.routes import router as members_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    configure_logging(configuration.log_level)
    engine, session_factory = create_session_factory(configuration)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="BridgeCart API", version="0.1.0", lifespan=lifespan)
    app.state.settings = configuration
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.login_limiter = LoginLimiter()

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc: RequestValidationError):  # type: ignore[no-untyped-def]
        # FastAPI normally echoes rejected input, including passwords and tokens.
        return JSONResponse(
            {"detail": [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]},
            status_code=422,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in configuration.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(members_router)
    app.include_router(api_keys_router)
    return app


app = create_app()
