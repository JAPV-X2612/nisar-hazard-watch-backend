from datetime import datetime

from pydantic import Field

from nisar_hazard_watch.constants.fire_context import FIRE_CONTEXT_SOURCE, FireContextStatus
from nisar_hazard_watch.models.base_model import CamelModel


class FireContext(CamelModel):
    status: FireContextStatus
    source: str = FIRE_CONTEXT_SOURCE
    window_start: datetime | None = None
    window_end: datetime | None = None
    detections: int | None = None
    low_confidence_excluded: int | None = None
    first_detection: datetime | None = None
    last_detection: datetime | None = None
    peak_frp_mw: float | None = None
    satellites: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    note: str
