from typing import Any

from pydantic import Field

from nisar_hazard_watch.constants.sar import AoiKind
from nisar_hazard_watch.models.base_model import CamelModel


class Aoi(CamelModel):
    kind: AoiKind
    geometry: dict[str, Any]
    wkt: str
    bbox: tuple[float, float, float, float]
    area_km2: float
    native_pixels: int
    warnings: list[str] = Field(default_factory=list)
