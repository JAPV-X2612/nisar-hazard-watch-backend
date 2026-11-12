from http import HTTPStatus

from fastapi import APIRouter, Response

from nisar_hazard_watch.api.dependencies import HealthServiceDep
from nisar_hazard_watch.constants.health import HealthStatus
from nisar_hazard_watch.constants.routes import LIVE_PATH
from nisar_hazard_watch.models.health import HealthResponse, LiveResponse

router = APIRouter(tags=["health"])


@router.get("", responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": HealthResponse}})
async def get_health(service: HealthServiceDep, response: Response) -> HealthResponse:
    report = await service.check()
    if report.status is HealthStatus.DOWN:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return report


@router.get(LIVE_PATH)
async def get_live() -> LiveResponse:
    return LiveResponse()
