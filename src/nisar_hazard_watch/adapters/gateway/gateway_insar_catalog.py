import logging
from datetime import date
from http import HTTPStatus
from typing import Any

import httpx

from nisar_hazard_watch.constants.insar import COVERAGE_PATH, GUNW_PRODUCT, SERIES_KEY
from nisar_hazard_watch.constants.sar import Direction
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError
from nisar_hazard_watch.models.insar_pair import InsarPair

logger = logging.getLogger(__name__)

PAIR_DATES = 2
UNAVAILABLE = "the GUNW pair catalog is unavailable"


class GatewayInsarCatalog:
    """GUNW pairs over a point, listed by the ML gateway from the public NISAR catalog."""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def pairs(
        self, longitude: float, latitude: float, start: date, end: date
    ) -> list[InsarPair]:
        params = {
            "longitude": longitude,
            "latitude": latitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "product": GUNW_PRODUCT,
        }
        try:
            response = await self._client.get(self._base_url + COVERAGE_PATH, params=params)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("GUNW pair catalog request failed: %s", type(exc).__name__)
            raise CatalogUnavailableError(UNAVAILABLE) from exc
        if response.status_code != HTTPStatus.OK or not isinstance(payload, dict):
            logger.warning("GUNW pair catalog answered %s", response.status_code)
            raise CatalogUnavailableError(UNAVAILABLE)
        found = [pair for series in payload.get("series") or [] for pair in _pairs_of(series)]
        return sorted(
            found, key=lambda pair: (pair.secondary_date, pair.reference_date), reverse=True
        )


def _pairs_of(series: dict[str, Any]) -> list[InsarPair]:
    key = SERIES_KEY.match(str(series.get("key", "")))
    if key is None:
        return []
    track, direction, frame, *_ = key.groups()
    found: list[InsarPair] = []
    for observation in series.get("observations") or []:
        try:
            dates = [date.fromisoformat(day) for day in observation["dates"]]
            if len(dates) != PAIR_DATES:
                continue
            reference, secondary = sorted(dates)
            found.append(
                InsarPair(
                    pair_id=str(observation["id"]),
                    series_key=str(series["key"]),
                    track=int(track),
                    direction=Direction(direction),
                    frame=int(frame),
                    reference_date=reference,
                    secondary_date=secondary,
                    temporal_baseline_days=(secondary - reference).days,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return found
