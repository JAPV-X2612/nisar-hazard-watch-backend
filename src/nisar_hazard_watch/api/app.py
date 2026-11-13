import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nisar_hazard_watch.adapters.db.engine import create_engine
from nisar_hazard_watch.api.body_limit_middleware import BodyLimitMiddleware
from nisar_hazard_watch.api.composition import (
    build_exploration_service,
    build_health_service,
    build_place_search_service,
)
from nisar_hazard_watch.api.error_handlers import register_error_handlers
from nisar_hazard_watch.api.request_id_middleware import RequestIdMiddleware
from nisar_hazard_watch.api.routes.router import register_routes
from nisar_hazard_watch.config.settings import Settings, get_settings
from nisar_hazard_watch.constants.explorations import BODY_LIMIT_BYTES
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER
from nisar_hazard_watch.constants.places import GEOCODER_USER_AGENT
from nisar_hazard_watch.ports.analysis_runner import AnalysisRunner
from nisar_hazard_watch.utils.logging import configure_logging
from nisar_hazard_watch.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ALLOWED_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]


RATE_WINDOW_SECONDS = 60.0


def create_app(
    settings: Settings | None = None,
    cmr_transport: httpx.AsyncBaseTransport | None = None,
    asf_transport: httpx.AsyncBaseTransport | None = None,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
    firms_transport: httpx.AsyncBaseTransport | None = None,
    geocoder_transport: httpx.AsyncBaseTransport | None = None,
    runner: AnalysisRunner | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(database_url=settings.database_url)
        try:
            async with (
                httpx.AsyncClient(
                    timeout=settings.cmr_health_timeout_seconds, transport=cmr_transport
                ) as http_client,
                httpx.AsyncClient(
                    timeout=settings.asf_timeout_seconds, transport=asf_transport
                ) as asf_client,
                httpx.AsyncClient(
                    timeout=settings.gateway_timeout_seconds, transport=gateway_transport
                ) as gateway_client,
                httpx.AsyncClient(
                    timeout=settings.firms_timeout_seconds, transport=firms_transport
                ) as firms_client,
                httpx.AsyncClient(
                    timeout=settings.geocoder_timeout_seconds,
                    transport=geocoder_transport,
                    headers={"User-Agent": GEOCODER_USER_AGENT.format(version=settings.version)},
                ) as geocoder_client,
            ):
                app.state.health_service = build_health_service(
                    settings=settings, engine=engine, http_client=http_client
                )
                app.state.exploration_service = build_exploration_service(
                    settings=settings,
                    engine=engine,
                    asf_client=asf_client,
                    gateway_client=gateway_client,
                    firms_client=firms_client,
                    runner=runner,
                )
                app.state.place_search_service = build_place_search_service(
                    settings=settings, geocoder_client=geocoder_client
                )
                app.state.rate_limiter = RateLimiter(
                    max_requests=settings.rate_limit_per_minute, window_seconds=RATE_WINDOW_SECONDS
                )
                app.state.trusted_proxy_hops = settings.trusted_proxy_hops
                logger.info(
                    "starting %s %s environment=%s cors_origins=%s",
                    settings.service_name,
                    settings.version,
                    settings.environment.value,
                    settings.cors_allowed_origins,
                )
                yield
        finally:
            await engine.dispose()

    app = FastAPI(title="NISAR Hazard Watch API", version=settings.version, lifespan=lifespan)
    # Middleware is added innermost first: errors -> body limit -> CORS -> request id (outermost).
    register_error_handlers(app=app)
    app.add_middleware(BodyLimitMiddleware, max_bytes=BODY_LIMIT_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=ALLOWED_METHODS,
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    register_routes(app=app)
    return app
