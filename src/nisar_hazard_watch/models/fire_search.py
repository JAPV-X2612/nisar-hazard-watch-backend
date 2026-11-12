from pydantic import Field

from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.fire_detection import FireDetection


class FireSearch(CamelModel):
    detections: list[FireDetection] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
