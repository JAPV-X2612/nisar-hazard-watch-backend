from typing import Protocol

from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.models.base_model import CamelModel


class PrecomputedCase(CamelModel):
    id: str
    title: str
    lens: Lens
    longitude: float
    latitude: float
    radius_km: float


class PrecomputedCases(Protocol):
    def find(self, longitude: float, latitude: float, lens: Lens) -> PrecomputedCase | None: ...
