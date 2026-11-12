from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nisar_hazard_watch.adapters.db.engine import create_engine
from nisar_hazard_watch.api.composition import build_health_service
from nisar_hazard_watch.api.error_handlers import register_error_handlers
from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.api.routes.router import register_routes
from nisar_hazard_watch.config.settings import Settings, get_settings
from nisar_hazard_watch.constants.routes import REQUEST_ID_HEADER
from nisar_hazard_watch.utils.logging import configure_logging

ALLOWED_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        async with httpx.AsyncClient(timeout=settings.cmr_health_timeout_seconds) as http_client:
            app.state.health_service = build_health_service(
                settings=settings, engine=engine, http_client=http_client
            )
            try:
                yield
            finally:
                await engine.dispose()

    app = FastAPI(title="NISAR Hazard Watch API", version=settings.version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=ALLOWED_METHODS,
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    register_routes(app)
    return app
