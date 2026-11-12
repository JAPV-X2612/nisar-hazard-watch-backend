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
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER
from tests.factories import QADIRABAD_LAT, QADIRABAD_LON

FIXTURE = Path(__file__).parents[4] / "fixtures" / "asf_qadirabad.json"
ALLOWED_ORIGIN = "https://nisar-hazard-watch-nine.vercel.app"
POINT = {"type": "Point", "coordinates": [QADIRABAD_LON, QADIRABAD_LAT]}
HUGE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.3, 0.0], [0.3, 0.3], [0.0, 0.3], [0.0, 0.0]]],
}
BODY = {"lens": "flood_wetland", "geometry": POINT}
URL = "/api/v1/explorations"
LONG_RUN_SECONDS = 10_000


def _asf_catalog(status: int = 200, features: list | None = None) -> httpx.MockTransport:
    body = json.loads(FIXTURE.read_text())
    if features is not None:
        body["features"] = features
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


@pytest.fixture
def start_api(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def start(
        runner: InProcessRunner | None = None,
        asf: httpx.MockTransport | None = None,
        **setting_overrides: object,
    ) -> TestClient:
        database = tmp_path / f"api-{len(clients)}.db"
        engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(engine)
        engine.dispose()
        settings = make_settings(
            **{
                "database_url": f"sqlite+aiosqlite:///{database}",
                "cors_allowed_origins": [ALLOWED_ORIGIN],
                "runner": RunnerKind.IN_PROCESS,
                "rate_limit_per_minute": 1000,
                **setting_overrides,
            }
        )
        app = create_app(
            settings=settings,
            asf_transport=asf or _asf_catalog(),
            runner=runner or InProcessRunner(),
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)


def test_a_finished_exploration_answers_200_with_camel_case_fields_and_honest_labels(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["id"].startswith("exp_")
    assert body["status"] == "succeeded"
    assert body["cache"] == "miss"
    assert body["plan"]["seriesKey"] == "084_A_018_4005_DHDH"
    assert len(body["plan"]["dates"]) == 5
    assert body["result"]["scientificStatus"] == "diagnostic"
    assert body["result"]["isDemo"] is True
    assert body["result"]["limitations"]
    assert body["result"]["layers"][0]["url"] == f"{URL}/{body['id']}/layers/display_synthetic"
    assert "etaSeconds" in body
    assert response.headers[REQUEST_ID_HEADER]


def test_a_running_exploration_answers_202_and_can_be_polled_and_cancelled(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(runner=InProcessRunner(duration_seconds=LONG_RUN_SECONDS))

    # Act
    created = client.post(url=URL, json=BODY)
    exploration_id = created.json()["id"]
    polled = client.get(url=f"{URL}/{exploration_id}")
    cancelled = client.delete(url=f"{URL}/{exploration_id}")

    # Assert
    assert created.status_code == 202
    assert created.json()["status"] == "running"
    assert polled.json()["status"] == "running"
    assert polled.json()["etaRemainingSeconds"] is not None
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["error"]["reasonCode"] == ReasonCode.CANCELLED


def test_the_same_request_twice_is_a_cache_hit(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()
    first = client.post(url=URL, json=BODY).json()

    # Act
    second = client.post(url=URL, json=BODY)

    # Assert
    assert second.status_code == 200
    assert second.json()["cache"] == "hit"
    assert second.json()["id"] == first["id"]


def test_a_layer_redirects_to_the_runners_artifact(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()
    created = client.post(url=URL, json=BODY).json()

    # Act
    response = client.get(
        url=f"{URL}/{created['id']}/layers/display_synthetic", follow_redirects=False
    )
    missing = client.get(url=f"{URL}/{created['id']}/layers/nope", follow_redirects=False)

    # Assert
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")
    assert missing.status_code == 404


@pytest.mark.parametrize(
    argnames=("body", "status", "reason"),
    argvalues=[
        ({**BODY, "source": "S"}, 422, ReasonCode.SOURCE_NOT_AVAILABLE),
        (
            {**BODY, "geometry": {"type": "Point", "coordinates": [500, 0]}},
            422,
            ReasonCode.INVALID_GEOMETRY,
        ),
        ({**BODY, "geometry": HUGE_POLYGON}, 422, ReasonCode.AREA_TOO_LARGE),
        ({**BODY, "lens": "landslide"}, 422, ReasonCode.INVALID_REQUEST),
        ({**BODY, "unexpected": True}, 422, ReasonCode.INVALID_REQUEST),
        ({"geometry": POINT}, 422, ReasonCode.INVALID_REQUEST),
    ],
    ids=["s-band", "bad-point", "too-large", "unknown-lens", "extra-field", "missing-lens"],
)
def test_invalid_requests_are_422_problems_with_their_reason_code(
    start_api: Callable[..., TestClient], body: dict, status: int, reason: ReasonCode
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.post(url=URL, json=body)

    # Assert
    assert response.status_code == status
    assert response.json()["reasonCode"] == reason


def test_a_failing_catalog_is_a_502_with_its_reason(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(asf=_asf_catalog(status=503))

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    assert response.status_code == 502
    assert response.json()["reasonCode"] == ReasonCode.UPSTREAM_CATALOG_ERROR


def test_an_area_without_scenes_is_a_final_no_data_answer(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(asf=_asf_catalog(features=[]))

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "noData"
    assert response.json()["error"]["reasonCode"] == ReasonCode.NO_COVERAGE


def test_a_full_queue_is_a_503_with_its_reason(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(
        runner=InProcessRunner(duration_seconds=LONG_RUN_SECONDS), max_active_explorations=1
    )
    client.post(url=URL, json=BODY)

    # Act
    response = client.post(url=URL, json={**BODY, "lens": "wildfire"})

    # Assert
    assert response.status_code == 503
    assert response.json()["reasonCode"] == ReasonCode.QUEUE_FULL


def test_each_client_is_limited_on_its_own_and_gets_a_429(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=2)
    first_client = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    other_client = {"X-Forwarded-For": "198.51.100.9"}

    # Act
    allowed = [client.post(url=URL, json=BODY, headers=first_client).status_code for _ in range(2)]
    limited = client.post(url=URL, json=BODY, headers=first_client)
    other = client.post(url=URL, json=BODY, headers=other_client)

    # Assert
    assert allowed == [200, 200]
    assert limited.status_code == 429
    assert limited.json()["reasonCode"] == ReasonCode.RATE_LIMITED
    assert other.status_code == 200


def test_an_oversized_body_is_refused_before_it_is_read(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    padding = {"type": "Point", "coordinates": [0, 0], "padding": "x" * 20_000}

    # Act
    response = client.post(url=URL, json={**BODY, "geometry": padding})

    # Assert
    assert response.status_code == 413
    assert response.json()["reasonCode"] == ReasonCode.PAYLOAD_TOO_LARGE


def test_unknown_and_malformed_ids_are_rejected(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()

    # Act
    unknown = client.get(url=f"{URL}/exp_0000000000000000")
    malformed = client.get(url=f"{URL}/not-an-id")

    # Assert
    assert unknown.status_code == 404
    assert unknown.json()["reasonCode"] == ReasonCode.NOT_FOUND
    assert malformed.status_code == 422


def test_the_lens_catalog_lists_the_four_supported_lenses(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(url="/api/v1/lenses")

    # Assert
    lenses = {lens["id"]: lens for lens in response.json()}
    assert set(lenses) == {"flood_wetland", "vegetation_disturbance", "wildfire", "agriculture"}
    assert lenses["agriculture"]["opticalEvidence"] is False
    assert lenses["flood_wetland"]["minimumDates"] == 4


def test_coverage_describes_the_plan_for_a_point(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(
        url="/api/v1/coverage", params={"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}
    )
    invalid = client.get(url="/api/v1/coverage", params={"lon": 500, "lat": 0})

    # Assert
    assert response.status_code == 200
    assert response.json()["plan"]["status"] == "ready"
    assert response.json()["plan"]["seriesKey"] == "084_A_018_4005_DHDH"
    assert invalid.status_code == 422


def test_the_openapi_document_lists_the_new_endpoints(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    paths = client.get(url="/openapi.json").json()["paths"]

    # Assert
    assert URL in paths
    assert f"{URL}/{{exploration_id}}" in paths
    assert f"{URL}/{{exploration_id}}/layers/{{layer_id}}" in paths
    assert "/api/v1/lenses" in paths
    assert "/api/v1/coverage" in paths
