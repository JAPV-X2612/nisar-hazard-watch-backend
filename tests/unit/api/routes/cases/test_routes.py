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
from nisar_hazard_watch.constants.errors import PROBLEM_CONTENT_TYPE, ReasonCode
from nisar_hazard_watch.constants.explorations import RunnerKind

CASES = Path(__file__).parents[4] / "fixtures" / "ml_gateway_cases.json"
GATEWAY_URL = "https://gateway.example.test"
URL = "/api/v1/cases"
QADIRABAD_SUMMARY = {
    "id": "qadirabad",
    "title": "Qadirabad / Chenab, Pakistan",
    "point": [73.713, 32.329],
    "status": "complete",
    "baselineDates": ["2026-06-20", "2026-07-02", "2026-07-14"],
    "assessmentDates": ["2026-07-26", "2026-08-19", "2026-08-31", "2026-09-12", "2026-09-24"],
}


def _gateway(status: int = 200) -> httpx.MockTransport:
    body = json.loads(CASES.read_text())
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


@pytest.fixture
def start_api(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def start(gateway: httpx.MockTransport, rate_limit: int = 1000) -> TestClient:
        database = tmp_path / f"cases-{len(clients)}.db"
        engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(engine)
        engine.dispose()
        settings = make_settings(
            database_url=f"sqlite+aiosqlite:///{database}",
            runner=RunnerKind.IN_PROCESS,
            rate_limit_per_minute=rate_limit,
            ml_gateway_url=GATEWAY_URL,
        )
        app = create_app(settings=settings, gateway_transport=gateway, runner=InProcessRunner())
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)


def test_the_cases_come_back_as_camel_case_summaries_in_the_gateway_order(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(url=URL)

    # Assert
    cases = response.json()["cases"]
    assert response.status_code == 200
    assert [case["id"] for case in cases] == [
        "chokwe",
        "qadirabad",
        "richmond",
        "kumamoto",
        "choco",
        "san-marcos",
    ]
    assert cases[1] == QADIRABAD_SUMMARY


def test_a_case_carries_its_grid_evidence_layers_and_limitations(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(url=f"{URL}/qadirabad")

    # Assert
    case = response.json()
    assert response.status_code == 200
    assert {key: case[key] for key in QADIRABAD_SUMMARY} == QADIRABAD_SUMMARY
    assert (len(case["layers"]), len(case["visualizations"])) == (8, 8)
    assert case["grid"] == {
        "crs": "EPSG:32643",
        "bounds": [376300.0, 3575080.0, 381420.0, 3580200.0],
        "shape": [128, 128],
        "postingM": [40.0, 40.0],
    }
    assert case["seriesKey"] == "084_A_018_4005_DHDH"
    assert (case["evidence"]["thresholdCells"], case["evidence"]["radarSupportCells"]) == (
        1911,
        16384,
    )
    assert "thresholdCellAreaHa" not in case["evidence"]
    assert (case["isDemo"], case["scientificStatus"], len(case["limitations"])) == (
        False,
        "diagnostic",
        7,
    )
    assert case["layers"][0]["url"] == f"{URL}/qadirabad/layers/change_db_hh"


def test_a_layer_redirects_to_the_png_on_the_gateway(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    layer = client.get(url=f"{URL}/qadirabad/layers/change_db_hh", follow_redirects=False)
    view = client.get(url=f"{URL}/qadirabad/layers/view_temporal_median_hh", follow_redirects=False)
    missing = client.get(url=f"{URL}/qadirabad/layers/nope", follow_redirects=False)

    # Assert
    assert layer.status_code == 307
    assert layer.headers["location"] == (
        f"{GATEWAY_URL}/v2/cases/qadirabad/layers/change_db_hh.png"
    )
    assert view.status_code == 307
    assert missing.status_code == 404
    assert missing.json()["reasonCode"] == ReasonCode.NOT_FOUND


def test_an_unknown_case_is_a_404_problem(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(url=f"{URL}/nope")

    # Assert
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert response.json()["reasonCode"] == ReasonCode.CASE_NOT_FOUND


def test_an_impossible_case_id_is_refused(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    response = client.get(url=f"{URL}/Bad!")

    # Assert
    assert response.status_code == 422


def test_a_gateway_outage_with_nothing_cached_is_a_502_problem(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway(status=503))

    # Act
    response = client.get(url=URL)

    # Assert
    assert response.status_code == 502
    assert response.json()["reasonCode"] == ReasonCode.CASES_UNAVAILABLE


def test_the_list_is_rate_limited_but_the_layers_are_not(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway(), rate_limit=1)
    client.get(url=URL)

    # Act
    limited = client.get(url=URL)
    layers = [
        client.get(url=f"{URL}/qadirabad/layers/change_db_hh", follow_redirects=False)
        for _ in range(3)
    ]

    # Assert
    assert limited.status_code == 429
    assert {layer.status_code for layer in layers} == {307}


def test_the_openapi_document_lists_the_case_endpoints(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    paths = client.get(url="/openapi.json").json()["paths"]

    # Assert
    assert {URL, f"{URL}/{{case_id}}", f"{URL}/{{case_id}}/layers/{{layer_id}}"} <= set(paths)


def test_the_openapi_document_names_the_known_case_statuses(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(gateway=_gateway())

    # Act
    schemas = client.get(url="/openapi.json").json()["components"]["schemas"]

    # Assert
    description = schemas["CaseSummary"]["properties"]["status"]["description"]
    for status in ("partial", "complete", "not_displacement_ready", "evaluated"):
        assert status in description
