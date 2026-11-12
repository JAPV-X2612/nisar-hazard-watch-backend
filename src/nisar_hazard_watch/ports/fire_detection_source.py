from datetime import date
from typing import Protocol

from nisar_hazard_watch.models.fire_search import FireSearch


class FireDetectionSource(Protocol):
    async def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> FireSearch:
        """Detections inside the box for the dates (inclusive); raises FireDataUnavailableError."""
        ...
