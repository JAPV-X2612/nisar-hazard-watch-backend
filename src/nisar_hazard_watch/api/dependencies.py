from typing import Annotated

from fastapi import Depends, Request

from nisar_hazard_watch.constants.routes import CLIENT_IP_HEADER
from nisar_hazard_watch.exceptions.exploration_errors import RateLimitedError
from nisar_hazard_watch.services.exploration_service import ExplorationService
from nisar_hazard_watch.services.health_service import HealthService
from nisar_hazard_watch.utils.rate_limiter import RateLimiter


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


def get_exploration_service(request: Request) -> ExplorationService:
    return request.app.state.exploration_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
ExplorationServiceDep = Annotated[ExplorationService, Depends(get_exploration_service)]


def client_key(request: Request) -> str:
    """The left-most forwarded address (the platform proxy sets it), else the socket peer."""
    forwarded = request.headers.get(CLIENT_IP_HEADER)
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    if not limiter.allow(client_key(request)):
        raise RateLimitedError("too many requests from this client; slow down and retry shortly")


RateLimit = Depends(enforce_rate_limit)
