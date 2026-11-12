from typing import Annotated

from fastapi import APIRouter, Query

from nisar_hazard_watch.api.dependencies import PlaceSearchServiceDep, RateLimit
from nisar_hazard_watch.constants.places import (
    DEFAULT_PLACE_LIMIT,
    MAX_PLACE_LIMIT,
    MAX_QUERY_LENGTH,
)
from nisar_hazard_watch.models.place import PlacesView

router = APIRouter(tags=["places"])

# The raw text may carry extra spaces; the service checks the trimmed length.
SearchText = Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH * 2)]
PlaceLimit = Annotated[int, Query(ge=1, le=MAX_PLACE_LIMIT)]


@router.get("", response_model=PlacesView, dependencies=[RateLimit])
async def search_places(
    q: SearchText, service: PlaceSearchServiceDep, limit: PlaceLimit = DEFAULT_PLACE_LIMIT
) -> PlacesView:
    return await service.search(query=q, limit=limit)
