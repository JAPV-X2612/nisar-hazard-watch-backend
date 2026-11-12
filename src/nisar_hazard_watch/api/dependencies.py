from typing import Annotated

from fastapi import Depends, Request

from nisar_hazard_watch.services.health_service import HealthService


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
