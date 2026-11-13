from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from nisar_hazard_watch.api.dependencies import InsarPairsServiceDep, RateLimit
from nisar_hazard_watch.models.insar_pairs import InsarPairsView

router = APIRouter(tags=["insar"])

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]


@router.get("/pairs", response_model=InsarPairsView, dependencies=[RateLimit])
async def list_pairs(
    lon: Longitude,
    lat: Latitude,
    service: InsarPairsServiceDep,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> InsarPairsView:
    return await service.pairs(longitude=lon, latitude=lat, start=start_date, end=end_date)
