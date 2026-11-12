from datetime import datetime
from typing import Protocol

from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene


class SarCatalog(Protocol):
    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]: ...
