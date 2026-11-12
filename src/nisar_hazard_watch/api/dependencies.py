from typing import Annotated

from fastapi import Depends, Request

from nisar_hazard_watch.constants.routes import CLIENT_IP_HEADER, UNKNOWN_CLIENT
from nisar_hazard_watch.exceptions.exploration_errors import RateLimitedError
from nisar_hazard_watch.hazards.earthquake.insar_pairs_service import InsarPairsService
from nisar_hazard_watch.services.exploration_service import ExplorationService
from nisar_hazard_watch.services.health_service import HealthService
from nisar_hazard_watch.utils.rate_limiter import RateLimiter


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


def get_exploration_service(request: Request) -> ExplorationService:
    return request.app.state.exploration_service


def get_insar_pairs_service(request: Request) -> InsarPairsService:
    return request.app.state.insar_pairs_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
ExplorationServiceDep = Annotated[ExplorationService, Depends(get_exploration_service)]
InsarPairsServiceDep = Annotated[InsarPairsService, Depends(get_insar_pairs_service)]


def client_key(request: Request, trusted_hops: int) -> str:
    """The address the outermost trusted proxy saw, counted from the right of the header.

    Clients can prepend any forwarded address, but cannot hide the ones our own proxies append.
    """
    forwarded = [
        address.strip()
        for address in request.headers.get(CLIENT_IP_HEADER, "").split(",")
        if address.strip()
    ]
    if trusted_hops and len(forwarded) >= trusted_hops:
        return forwarded[-trusted_hops]
    return request.client.host if request.client else UNKNOWN_CLIENT


async def enforce_rate_limit(
    request: Request, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    if not limiter.allow(
        client_key(request=request, trusted_hops=request.app.state.trusted_proxy_hops)
    ):
        raise RateLimitedError("too many requests from this client; slow down and retry shortly")


RateLimit = Depends(enforce_rate_limit)
