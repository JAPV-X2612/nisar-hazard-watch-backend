import asyncio
import logging
from datetime import date, timedelta
from http import HTTPStatus

import httpx
from pydantic import SecretStr

from nisar_hazard_watch.adapters.firms.detection_parser import is_detection_csv, parse_detections
from nisar_hazard_watch.constants.fire_context import (
    FIRMS_AREA_PATH,
    FIRMS_BODY_LOG_CHARS,
    FIRMS_CONCURRENCY,
    FIRMS_MAX_DAY_RANGE,
    FIRMS_SERVER_ERROR_FLOOR,
    FirmsProduct,
)
from nisar_hazard_watch.exceptions.fire_data_errors import FireDataUnavailableError
from nisar_hazard_watch.models.fire_detection import FireDetection
from nisar_hazard_watch.models.fire_search import FireSearch

logger = logging.getLogger(__name__)

HALF_TURN = 180.0
Box = tuple[float, float, float, float]


def _boxes(bbox: Box) -> list[Box]:
    west, south, east, north = bbox
    if west <= east:
        return [bbox]
    return [(west, south, HALF_TURN, north), (-HALF_TURN, south, east, north)]


def _chunks(start: date, end: date) -> list[tuple[date, int]]:
    chunks: list[tuple[date, int]] = []
    cursor = start
    while cursor <= end:
        days = min(FIRMS_MAX_DAY_RANGE, (end - cursor).days + 1)
        chunks.append((cursor, days))
        cursor += timedelta(days=days)
    return chunks


def _identity(detection: FireDetection) -> tuple[float, float, str, str]:
    return (
        round(detection.latitude, 5),
        round(detection.longitude, 5),
        detection.detected_at.isoformat(),
        detection.satellite,
    )


class FirmsClient:
    """NASA FIRMS area API: VIIRS detections as CSV, at most five days per request."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, map_key: SecretStr) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._map_key = map_key

    async def search(self, bbox: Box, start: date, end: date) -> FireSearch:
        gate = asyncio.Semaphore(FIRMS_CONCURRENCY)
        requests = [
            self._fetch(product=product, box=box, start=chunk_start, days=days, gate=gate)
            for product in FirmsProduct
            for box in _boxes(bbox=bbox)
            for chunk_start, days in _chunks(start=start, end=end)
        ]
        answers = await asyncio.gather(*requests, return_exceptions=True)
        failures = [answer for answer in answers if isinstance(answer, BaseException)]
        if failures:
            raise FireDataUnavailableError(reason=self._reason(failure=failures[0]))
        served = [answer for answer in answers if not isinstance(answer, BaseException)]
        products = sorted({product for product, rows in served if rows is not None})
        if not products:
            raise FireDataUnavailableError(reason="FIRMS served no data for these dates")
        unique = {
            _identity(detection=detection): detection
            for _, rows in served
            for detection in rows or []
        }
        return FireSearch(detections=list(unique.values()), products=products)

    async def _fetch(
        self, product: FirmsProduct, box: Box, start: date, days: int, gate: asyncio.Semaphore
    ) -> tuple[str, list[FireDetection] | None]:
        west, south, east, north = box
        path = FIRMS_AREA_PATH.format(
            map_key=self._map_key.get_secret_value(),
            product=product.value,
            west=f"{west:.4f}",
            south=f"{south:.4f}",
            east=f"{east:.4f}",
            north=f"{north:.4f}",
            days=days,
            start=start.isoformat(),
        )
        async with gate:
            response = await self._client.get(self._base_url + path)
        if (
            response.status_code >= FIRMS_SERVER_ERROR_FLOOR
            or response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        ):
            raise FireDataUnavailableError(reason=f"FIRMS answered {response.status_code}")
        if response.status_code != HTTPStatus.OK or not is_detection_csv(text=response.text):
            logger.warning(
                "FIRMS did not serve %s from %s: status %s, %r",
                product.value,
                start,
                response.status_code,
                self._scrub(text=response.text[:FIRMS_BODY_LOG_CHARS]),
            )
            return product.value, None
        return product.value, parse_detections(text=response.text)

    def _scrub(self, text: str) -> str:
        return text.replace(self._map_key.get_secret_value(), "***")

    @staticmethod
    def _reason(failure: BaseException) -> str:
        if isinstance(failure, FireDataUnavailableError):
            return failure.reason
        return f"FIRMS could not be reached ({type(failure).__name__})"
