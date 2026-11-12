from fastapi import APIRouter

from nisar_hazard_watch.models.exploration import LensInfo
from nisar_hazard_watch.services.lens_catalog import list_lenses

router = APIRouter(tags=["lenses"])


@router.get("", response_model=list[LensInfo])
async def get_lenses() -> list[LensInfo]:
    return list_lenses()
