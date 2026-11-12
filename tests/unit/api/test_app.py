from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.constants.routes import REQUEST_ID_HEADER

ALLOWED_ORIGIN = "https://nisar-hazard-watch-nine.vercel.app"
OTHER_ORIGIN = "https://evil.example.test"
UNREACHABLE_CMR_URL = "http://127.0.0.1:9/health"


@pytest.fixture(autouse=True)
def isolated_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env file is picked up


@pytest.fixture
def app_settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite://",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        cmr_health_url=UNREACHABLE_CMR_URL,
        cmr_health_timeout_seconds=0.5,
    )


@pytest.fixture
def client(app_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(app_settings)) as test_client:
        yield test_client


def _preflight(client: TestClient, origin: str) -> Response:
    return client.options(
        "/api/v1/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_cors_allows_the_configured_origin_only(client: TestClient) -> None:
    # Arrange / Act
    allowed = _preflight(client, ALLOWED_ORIGIN)
    blocked = _preflight(client, OTHER_ORIGIN)

    # Assert
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-origin" not in blocked.headers


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    # Arrange / Act
    response = client.get("/api/v1/health/live")

    # Assert
    assert response.headers[REQUEST_ID_HEADER]


def test_the_openapi_document_lists_the_health_endpoints(client: TestClient) -> None:
    # Arrange / Act
    paths = client.get("/openapi.json").json()["paths"]

    # Assert
    assert "/api/v1/health" in paths
    assert "/api/v1/health/live" in paths


def test_the_lifespan_wires_the_health_service_and_degrades_when_nasa_is_unreachable(
    client: TestClient,
) -> None:
    # Arrange / Act
    response = client.get("/api/v1/health")

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == HealthStatus.DEGRADED
    assert body["dependencies"][DependencyName.DATABASE]["state"] == DependencyState.OK
    assert body["dependencies"][DependencyName.CMR]["state"] == DependencyState.DOWN
