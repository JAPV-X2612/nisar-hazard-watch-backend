from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus

ALLOWED_ORIGIN = "https://nisar-hazard-watch-nine.vercel.app"
OTHER_ORIGIN = "https://evil.example.test"
HEALTHY_CMR_BODY = {"echo": {"ok?": True}, "indexer": {"ok?": True}}
UNEXPECTED_MESSAGE = "secret unexpected detail"


def _cmr_unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no route", request=request)


def _cmr_healthy(request: httpx.Request) -> httpx.Response:
    return httpx.Response(status_code=200, json=HEALTHY_CMR_BODY)


@pytest.fixture
def app_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(cors_allowed_origins=[ALLOWED_ORIGIN])


@pytest.fixture
def client(app_settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings=app_settings, cmr_transport=httpx.MockTransport(_cmr_unreachable))
    with TestClient(app) as test_client:
        yield test_client


def _preflight(client: TestClient, origin: str) -> Response:
    return client.options(
        url="/api/v1/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_cors_allows_the_configured_origin_only(client: TestClient) -> None:
    # Arrange
    allowed_origin, blocked_origin = ALLOWED_ORIGIN, OTHER_ORIGIN

    # Act
    allowed = _preflight(client=client, origin=allowed_origin)
    blocked = _preflight(client=client, origin=blocked_origin)

    # Assert
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-origin" not in blocked.headers


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    # Arrange
    path = "/api/v1/health/live"

    # Act
    response = client.get(url=path)

    # Assert
    assert response.headers[REQUEST_ID_HEADER]


def test_the_openapi_document_lists_the_health_endpoints(client: TestClient) -> None:
    # Arrange
    path = "/openapi.json"

    # Act
    paths = client.get(url=path).json()["paths"]

    # Assert
    assert "/api/v1/health" in paths
    assert "/api/v1/health/live" in paths


def test_health_degrades_when_nasa_is_unreachable(client: TestClient) -> None:
    # Arrange
    path = "/api/v1/health"

    # Act
    response = client.get(url=path)

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == HealthStatus.DEGRADED
    assert body["dependencies"][DependencyName.DATABASE]["state"] == DependencyState.OK
    assert body["dependencies"][DependencyName.CMR]["state"] == DependencyState.DOWN


def test_health_is_ok_when_every_dependency_answers(app_settings: Settings) -> None:
    # Arrange
    app = create_app(settings=app_settings, cmr_transport=httpx.MockTransport(_cmr_healthy))

    # Act
    with TestClient(app) as test_client:
        response = test_client.get(url="/api/v1/health")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == HealthStatus.OK


def test_an_unexpected_error_still_carries_cors_and_the_request_id(
    app_settings: Settings,
) -> None:
    # Arrange
    app = create_app(settings=app_settings, cmr_transport=httpx.MockTransport(_cmr_healthy))

    async def boom() -> None:
        raise RuntimeError(UNEXPECTED_MESSAGE)

    app.add_api_route(path="/boom", endpoint=boom)

    # Act
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get(url="/boom", headers={"Origin": ALLOWED_ORIGIN})

    # Assert
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers[REQUEST_ID_HEADER] == response.json()["requestId"]
    assert UNEXPECTED_MESSAGE not in response.text
