from datetime import date
from typing import Protocol

from nisar_hazard_watch.models.insar_pair import InsarPair


class InsarPairCatalog(Protocol):
    async def pairs(
        self, longitude: float, latitude: float, start: date, end: date
    ) -> list[InsarPair]:
        """GUNW pairs over the point with both acquisitions in the window, newest first."""
        ...
