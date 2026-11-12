from fastapi import APIRouter, Response

from nisar_hazard_watch.api.dependencies import HealthServiceDep
from nisar_hazard_watch.constants.health import HealthStatus
from nisar_hazard_watch.constants.routes import LIVE_PATH
from nisar_hazard_watch.models.health import HealthResponse, LiveResponse

router = APIRouter(tags=["health"])


@router.get("", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def get_health(service: HealthServiceDep, response: Response) -> HealthResponse:
    report = await service.check()
    if report.status is HealthStatus.DOWN:
        response.status_code = 503
    return report


@router.get(LIVE_PATH, response_model=LiveResponse)
async def get_live() -> LiveResponse:
    return LiveResponse()
