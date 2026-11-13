from fastapi import APIRouter, FastAPI

from nisar_hazard_watch.api.routes.coverage.routes import router as coverage_router
from nisar_hazard_watch.api.routes.explorations.routes import router as explorations_router
from nisar_hazard_watch.api.routes.health.routes import router as health_router
from nisar_hazard_watch.api.routes.lenses.routes import router as lenses_router
from nisar_hazard_watch.api.routes.places.routes import router as places_router
from nisar_hazard_watch.constants.routes import (
    API_PREFIX,
    COVERAGE_PREFIX,
    EXPLORATIONS_PREFIX,
    HEALTH_PREFIX,
    LENSES_PREFIX,
    PLACES_PREFIX,
)

ROUTERS: tuple[tuple[APIRouter, str], ...] = (
    (health_router, HEALTH_PREFIX),
    (explorations_router, EXPLORATIONS_PREFIX),
    (lenses_router, LENSES_PREFIX),
    (coverage_router, COVERAGE_PREFIX),
    (places_router, PLACES_PREFIX),
)


def register_routes(app: FastAPI) -> None:
    for router, prefix in ROUTERS:
        app.include_router(router, prefix=f"{API_PREFIX}{prefix}")
