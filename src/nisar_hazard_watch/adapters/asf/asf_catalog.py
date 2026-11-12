import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from shapely import from_wkt
from shapely.geometry import shape

from nisar_hazard_watch.adapters.asf.scene_parser import parse_scene_identity
from nisar_hazard_watch.constants.sar import ASF_SEARCH_URL, CATALOG_MAX_RESULTS
from nisar_hazard_watch.exceptions.catalog_errors import (
    CatalogTruncatedError,
    CatalogUnavailableError,
)
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene

logger = logging.getLogger(__name__)

ASF_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
COVERAGE_DECIMALS = 3


class AsfCatalog:
    """Public NASA ASF SearchAPI: no authentication, no maturity or configuration filter."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = ASF_SEARCH_URL,
        max_results: int = CATALOG_MAX_RESULTS,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._max_results = max_results

    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]:
        features = await self._features(aoi=aoi, start=start, end=end)
        if len(features) >= self._max_results:
            raise CatalogTruncatedError(
                f"the catalog returned {len(features)} products, the maximum requested; "
                "the list may be incomplete"
            )
        aoi_shape = from_wkt(aoi.wkt)
        scenes = (self._to_scene(feature=f, aoi_shape=aoi_shape) for f in features)
        return [scene for scene in scenes if scene is not None]

    async def _features(self, aoi: Aoi, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {
            "dataset": "NISAR",
            "processingLevel": "GCOV",
            "intersectsWith": aoi.wkt,
            "start": start.astimezone(UTC).strftime(ASF_TIME_FORMAT),
            "end": end.astimezone(UTC).strftime(ASF_TIME_FORMAT),
            "maxResults": self._max_results,
            "output": "geojson",
        }
        try:
            response = await self._client.get(self._base_url, params=params)
            response.raise_for_status()
            features = response.json()["features"]
            if not isinstance(features, list):
                raise TypeError("features is not a list")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("ASF catalog request failed", exc_info=True)
            raise CatalogUnavailableError("the ASF scene catalog did not answer correctly") from exc
        return features

    @staticmethod
    def _to_scene(feature: dict[str, Any], aoi_shape: Any) -> Scene | None:
        properties = feature.get("properties") or {}
        identity = parse_scene_identity(
            scene_name=properties.get("sceneName", ""), url=properties.get("url", "")
        )
        footprint = feature.get("geometry")
        if identity is None or not footprint:
            return None
        shape_ = shape(footprint)
        if not shape_.is_valid:
            shape_ = shape_.buffer(0)
        overlap = shape_.intersection(aoi_shape).area / aoi_shape.area
        return Scene(**identity.model_dump(), coverage=round(overlap, COVERAGE_DECIMALS))
