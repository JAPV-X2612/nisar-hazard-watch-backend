from typing import Annotated

from fastapi import APIRouter, Query

from nisar_hazard_watch.api.dependencies import ExplorationServiceDep, RateLimit
from nisar_hazard_watch.models.exploration import CoverageView

router = APIRouter(tags=["coverage"])

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]


@router.get("", response_model=CoverageView, dependencies=[RateLimit])
async def get_coverage(
    lon: Longitude, lat: Latitude, service: ExplorationServiceDep
) -> CoverageView:
    return await service.coverage(geometry={"type": "Point", "coordinates": [lon, lat]})
