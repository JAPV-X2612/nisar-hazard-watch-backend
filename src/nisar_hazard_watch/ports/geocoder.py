from typing import Protocol

from nisar_hazard_watch.models.place import PlaceView


class Geocoder(Protocol):
    async def search(self, query: str, limit: int) -> list[PlaceView]: ...
