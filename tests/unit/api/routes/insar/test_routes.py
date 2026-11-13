import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from nisar_hazard_watch.adapters.db.models import Base
from nisar_hazard_watch.adapters.runners.in_process_runner import InProcessRunner
from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import RunnerKind

COVERAGE = Path(__file__).parents[4] / "fixtures" / "ml_gateway_coverage_gunw.json"
URL = "/api/v1/insar/pairs"
POINT_QUERY = {"lon": 130.65, "lat": 32.65}
PAIR_COUNT = 23


def _gateway(status: int = 200) -> httpx.MockTransport:
    body = json.loads(COVERAGE.read_text())
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


@pytest.fixture
def start_api(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def start(gateway: httpx.MockTransport) -> TestClient:
        database = tmp_path / f"insar-{len(clients)}.db"
        engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(engine)
        engine.dispose()
        settings = make_settings(
            database_url=f"sqlite+aiosqlite:///{database}",
            runner=RunnerKind.IN_PROCESS,
            rate_limit_per_minute=1000,
        )
        app = create_app(settings=settings, gateway_transport=gateway, runner=InProcessRunner())
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)


def test_the_pairs_over_a_point_come_back_newest_first_in_camel_case(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(
        url=URL, params={**POINT_QUERY, "startDate": "2026-06-01", "endDate": "2026-11-12"}
    )

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert (body["windowStart"], body["windowEnd"]) == ("2026-06-01", "2026-11-12")
    assert len(body["pairs"]) == PAIR_COUNT
    first = body["pairs"][0]
    assert first["secondaryDate"] == "2026-10-20"
    assert set(first) == {
        "pairId",
        "seriesKey",
        "track",
        "direction",
        "frame",
        "referenceDate",
        "secondaryDate",
        "temporalBaselineDays",
    }


def test_an_unusable_window_is_a_422_problem(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(
        url=URL, params={**POINT_QUERY, "startDate": "2026-08-01", "endDate": "2026-07-01"}
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["reasonCode"] == ReasonCode.INVALID_REQUEST


def test_a_gateway_outage_is_a_502_catalog_problem(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(gateway=_gateway(status=503))

    # Act
    response = client.get(url=URL, params=POINT_QUERY)

    # Assert
    assert response.status_code == 502
    assert response.json()["reasonCode"] == ReasonCode.UPSTREAM_CATALOG_ERROR


@pytest.mark.parametrize(argnames="params", argvalues=[{"lon": 200, "lat": 0}, {"lon": 0}])
def test_a_missing_or_impossible_coordinate_is_refused(
    start_api: Callable[..., TestClient], params: dict
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(url=URL, params=params)

    # Assert
    assert response.status_code == 422
