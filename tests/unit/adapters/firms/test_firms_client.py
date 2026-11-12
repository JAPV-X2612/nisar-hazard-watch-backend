import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from nisar_hazard_watch.adapters.firms.firms_client import FirmsClient
from nisar_hazard_watch.exceptions.fire_data_errors import FireDataUnavailableError

FIXTURE = Path(__file__).parents[3] / "fixtures" / "firms_viirs_noaa20_area.csv"
BASE_URL = "https://firms.example.test"
MAP_KEY = "secret-map-key-123"
BBOX = (11.0, 0.0, 12.0, 1.0)
ANTIMERIDIAN_BBOX = (179.5, -17.0, -179.5, -16.0)
THIRTEEN_DAYS = (date(2026, 11, 1), date(2026, 11, 13))
PRODUCT_COUNT = 4
ROW_COUNT = 13
EXPECTED_DAY_RANGES = ["5", "5", "3"]
REFUSAL = f"Invalid MAP_KEY {MAP_KEY}."


class Recorder:
    def __init__(self, answer: httpx.Response | Exception | None = None) -> None:
        self.urls: list[str] = []
        self._answer = answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer or httpx.Response(status_code=200, text=FIXTURE.read_text())


async def _search(handler: Recorder, bbox: tuple = BBOX, dates: tuple = THIRTEEN_DAYS):
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        source = FirmsClient(client=client, base_url=BASE_URL, map_key=SecretStr(MAP_KEY))
        return await source.search(bbox=bbox, start=dates[0], end=dates[1])


async def test_a_thirteen_day_window_is_asked_in_five_five_and_three_day_requests() -> None:
    # Arrange
    handler = Recorder()

    # Act
    await _search(handler=handler)

    # Assert
    assert len(handler.urls) == PRODUCT_COUNT * len(EXPECTED_DAY_RANGES)
    first_product = [url for url in handler.urls if "/VIIRS_SNPP_SP/" in url]
    assert [url.split("/")[-2] for url in first_product] == EXPECTED_DAY_RANGES
    assert first_product[0] == (
        f"{BASE_URL}/api/area/csv/{MAP_KEY}/VIIRS_SNPP_SP/11.0000,0.0000,12.0000,1.0000/5/2026-11-01"
    )
    assert first_product[2].endswith("/3/2026-11-11")


async def test_a_detection_served_by_archive_and_near_real_time_counts_once() -> None:
    # Arrange
    handler = Recorder()

    # Act
    search = await _search(handler=handler, dates=(date(2026, 11, 11), date(2026, 11, 12)))

    # Assert
    assert len(search.detections) == ROW_COUNT
    assert search.products == [
        "VIIRS_NOAA20_NRT",
        "VIIRS_NOAA20_SP",
        "VIIRS_SNPP_NRT",
        "VIIRS_SNPP_SP",
    ]


async def test_a_product_that_answers_with_a_sentence_is_left_out_not_treated_as_no_fires() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if "_SP/" in str(request.url):
            return httpx.Response(status_code=200, text=FIXTURE.read_text())
        return httpx.Response(status_code=200, text="No data for these dates")

    # Act
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        source = FirmsClient(client=client, base_url=BASE_URL, map_key=SecretStr(MAP_KEY))
        search = await source.search(bbox=BBOX, start=date(2026, 11, 11), end=date(2026, 11, 12))

    # Assert
    assert search.products == ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP"]
    assert len(search.detections) == ROW_COUNT


async def test_when_no_product_serves_data_the_context_is_unavailable() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, text="Invalid MAP_KEY."))

    # Act / Assert
    with pytest.raises(expected_exception=FireDataUnavailableError, match="served no data"):
        await _search(handler=handler)


@pytest.mark.parametrize(argnames="status", argvalues=[429, 500, 503])
async def test_rate_limits_and_server_errors_make_the_context_unavailable(status: int) -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=status, text="busy"))

    # Act / Assert
    with pytest.raises(expected_exception=FireDataUnavailableError, match=str(status)):
        await _search(handler=handler)


async def test_an_unreachable_service_makes_the_context_unavailable() -> None:
    # Arrange
    handler = Recorder(answer=httpx.ConnectTimeout("slow"))

    # Act / Assert
    with pytest.raises(expected_exception=FireDataUnavailableError, match="ConnectTimeout"):
        await _search(handler=handler)


async def test_a_box_across_the_antimeridian_is_asked_as_two_boxes() -> None:
    # Arrange
    handler = Recorder()

    # Act
    await _search(handler=handler, bbox=ANTIMERIDIAN_BBOX, dates=(date(2026, 11, 11),) * 2)

    # Assert
    boxes = {url.split("/")[-3] for url in handler.urls}
    assert boxes == {"179.5000,-17.0000,180.0000,-16.0000", "-180.0000,-17.0000,-179.5000,-16.0000"}


async def test_the_map_key_never_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, text=REFUSAL))

    # Act
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(expected_exception=FireDataUnavailableError),
    ):
        await _search(handler=handler)

    # Assert
    assert caplog.records
    assert MAP_KEY not in caplog.text
