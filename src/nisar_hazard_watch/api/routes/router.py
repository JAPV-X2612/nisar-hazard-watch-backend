from fastapi import APIRouter, FastAPI

from nisar_hazard_watch.api.routes.health.routes import router as health_router
from nisar_hazard_watch.constants.routes import API_PREFIX, HEALTH_PREFIX

ROUTERS: tuple[tuple[APIRouter, str], ...] = ((health_router, HEALTH_PREFIX),)


def register_routes(app: FastAPI) -> None:
    for router, prefix in ROUTERS:
        app.include_router(router, prefix=f"{API_PREFIX}{prefix}")
