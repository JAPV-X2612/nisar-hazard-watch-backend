import json
import math
from pathlib import Path

from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.ports.precomputed_cases import PrecomputedCase

EARTH_RADIUS_KM = 6371.0088


def _distance_km(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_lambda = math.radians(lon_b - lon_a)
    haversine = (
        math.sin((phi_b - phi_a) / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


class StaticPrecomputedCases:
    """Cases measured ahead of time; a request near one can be offered it when live data fails."""

    def __init__(self, cases: list[PrecomputedCase]) -> None:
        self._cases = cases

    @classmethod
    def from_file(cls, path: str | None) -> "StaticPrecomputedCases":
        if not path:
            return cls(cases=[])
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(cases=[PrecomputedCase.model_validate(item) for item in payload])

    def find(self, longitude: float, latitude: float, lens: Lens) -> PrecomputedCase | None:
        nearby = [
            (distance, case)
            for case in self._cases
            if case.lens is lens
            and (distance := _distance_km(longitude, latitude, case.longitude, case.latitude))
            <= case.radius_km
        ]
        return min(nearby, key=lambda item: item[0])[1] if nearby else None
