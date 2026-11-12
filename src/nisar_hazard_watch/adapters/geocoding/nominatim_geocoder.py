import logging
from typing import Any

import httpx

from nisar_hazard_watch.constants.places import (
    DEFAULT_GEOCODER_URL,
    GEOCODER_LANGUAGE,
    GEOCODER_RESPONSE_FORMAT,
)
from nisar_hazard_watch.exceptions.place_errors import GeocoderUnavailableError
from nisar_hazard_watch.models.place import PlaceView

logger = logging.getLogger(__name__)

OSM_TYPE_INITIALS = {"node": "n", "way": "w", "relation": "r"}


class NominatimGeocoder:
    """OpenStreetMap's Nominatim, reached only at the host the deployment configures."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = DEFAULT_GEOCODER_URL) -> None:
        self._client = client
        self._base_url = base_url

    async def search(self, query: str, limit: int) -> list[PlaceView]:
        items = await self._items(query=query, limit=limit)
        places = [place for item in items if (place := self._to_place(item=item)) is not None]
        if items and not places:
            raise GeocoderUnavailableError(
                f"none of the {len(items)} places could be read; "
                "the provider format may have changed"
            )
        return places

    async def _items(self, query: str, limit: int) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": GEOCODER_RESPONSE_FORMAT,
            "limit": limit,
            "accept-language": GEOCODER_LANGUAGE,
            "addressdetails": 0,
            "dedupe": 1,
        }
        try:
            response = await self._client.get(self._base_url, params=params)
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list):
                raise TypeError("the answer is not a list")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("geocoder request failed", exc_info=True)
            raise GeocoderUnavailableError("the place search did not answer correctly") from exc
        return items

    @staticmethod
    def _to_place(item: dict[str, Any]) -> PlaceView | None:
        try:
            display_name = str(item["display_name"])
            return PlaceView(
                id=f"{OSM_TYPE_INITIALS.get(str(item['osm_type']), 'x')}{item['osm_id']}",
                name=str(item.get("name") or display_name.split(",")[0]).strip(),
                display_name=display_name,
                kind=str(item.get("addresstype") or item.get("type") or "place"),
                point=(float(item["lon"]), float(item["lat"])),
                bbox=NominatimGeocoder._bbox(item=item),
                importance=float(item.get("importance") or 0.0),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("skipping an unreadable place", exc_info=True)
            return None

    @staticmethod
    def _bbox(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
        try:
            south, north, west, east = (float(value) for value in item["boundingbox"])
        except (KeyError, TypeError, ValueError):
            return None
        return (west, south, east, north)
