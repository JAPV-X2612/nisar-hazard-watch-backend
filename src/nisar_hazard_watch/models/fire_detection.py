from datetime import datetime

from nisar_hazard_watch.models.base_model import CamelModel


class FireDetection(CamelModel):
    latitude: float
    longitude: float
    detected_at: datetime
    satellite: str
    confidence: str
    frp_mw: float | None = None
