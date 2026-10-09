from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bridgecart.core.config import Settings, get_settings
from bridgecart.core.logging import configure_logging
from bridgecart.db.session import create_session_factory
from bridgecart.health.routes import router as health_router


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in configuration.cors_origins.split(",")],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    return app


app = create_app()
