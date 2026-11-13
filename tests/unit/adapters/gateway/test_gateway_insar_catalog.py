import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.gateway.gateway_insar_catalog import GatewayInsarCatalog
from nisar_hazard_watch.constants.sar import Direction
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_coverage_gunw.json"
BASE_URL = "https://gateway.example.test"
KUMAMOTO = (130.65, 32.65)
START, END = date(2026, 6, 1), date(2026, 11, 12)
PAIR_COUNT = 23
NEWEST_SECONDARY = date(2026, 10, 20)
KUMAMOTO_PAIR_SUFFIX = "20260721T202900_20260721T202934_20260814T202858_20260814T202933"


class Recorder:
    def __init__(self, answer: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._answer = answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _real_answer() -> httpx.Response:
    return httpx.Response(status_code=200, json=json.loads(FIXTURE.read_text()))


async def _pairs(handler: Recorder):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = GatewayInsarCatalog(client=client, base_url=BASE_URL)
        return await catalog.pairs(
            longitude=KUMAMOTO[0], latitude=KUMAMOTO[1], start=START, end=END
        )


async def test_it_lists_every_real_pair_newest_first_with_its_series_identity() -> None:
    # Arrange
    handler = Recorder(answer=_real_answer())

    # Act
    pairs = await _pairs(handler=handler)

    # Assert
    assert len(pairs) == PAIR_COUNT
    assert pairs[0].secondary_date == NEWEST_SECONDARY
    assert [pair.secondary_date for pair in pairs] == sorted(
        (pair.secondary_date for pair in pairs), reverse=True
    )
    kumamoto = next(pair for pair in pairs if KUMAMOTO_PAIR_SUFFIX in pair.pair_id)
    assert (kumamoto.track, kumamoto.direction, kumamoto.frame) == (24, Direction.ASCENDING, 18)
    assert kumamoto.series_key == "024_A_018_4000_SH"
    assert kumamoto.temporal_baseline_days == 24


async def test_it_asks_the_gateway_for_gunw_over_the_point_and_the_window() -> None:
    # Arrange
    handler = Recorder(answer=_real_answer())

    # Act
    await _pairs(handler=handler)

    # Assert
    assert handler.requests[0].url.path == "/v2/coverage"
    assert dict(handler.requests[0].url.params) == {
        "longitude": "130.65",
        "latitude": "32.65",
        "start_date": "2026-06-01",
        "end_date": "2026-11-12",
        "product": "GUNW",
    }


async def test_entries_that_cannot_be_read_are_skipped_not_fatal() -> None:
    # Arrange
    body = {
        "series": [
            {"key": "not-a-series-key", "observations": [{"id": "x", "dates": ["2026-07-01"]}]},
            {
                "key": "024_A_018_4000_SH",
                "observations": [
                    {"id": "one-date-only", "dates": ["2026-07-09"]},
                    {"id": "bad-date", "dates": ["2026-07-09", "soon"]},
                    {"dates": ["2026-07-09", "2026-07-21"]},
                    {"id": "ok", "dates": ["2026-07-21", "2026-07-09"]},
                ],
            },
        ]
    }
    handler = Recorder(answer=httpx.Response(status_code=200, json=body))

    # Act
    pairs = await _pairs(handler=handler)

    # Assert
    assert [pair.pair_id for pair in pairs] == ["ok"]
    assert (pairs[0].reference_date, pairs[0].secondary_date) == (
        date(2026, 7, 9),
        date(2026, 7, 21),
    )


@pytest.mark.parametrize(
    argnames="answer",
    argvalues=[
        httpx.Response(status_code=502, json={"code": "catalog_unavailable"}),
        httpx.Response(status_code=422, json={"code": "catalog_limit"}),
        httpx.Response(status_code=200, text="not json"),
        httpx.Response(status_code=200, json=["unexpected"]),
        httpx.ConnectTimeout("slow"),
    ],
    ids=["gateway error", "window too wide", "not json", "unexpected body", "unreachable"],
)
async def test_a_failing_gateway_is_reported_as_an_unavailable_catalog(
    answer: httpx.Response | Exception,
) -> None:
    # Arrange
    handler = Recorder(answer=answer)

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError):
        await _pairs(handler=handler)
