from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.dependencies import get_health_service
from nisar_hazard_watch.api.routes.router import register_routes
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.models.health import DependencyReport, HealthResponse
from tests.constants import SERVICE_NAME, SERVICE_VERSION

CHECKED_AT = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
LATENCY_MS = 1.5


class StubHealthService:
    def __init__(self, status: HealthStatus) -> None:
        self._status = status

    async def check(self) -> HealthResponse:
        state = DependencyState.DOWN if self._status is HealthStatus.DOWN else DependencyState.OK
        return HealthResponse(
            status=self._status,
            service=SERVICE_NAME,
            version=SERVICE_VERSION,
            environment=Environment.TEST,
            checked_at=CHECKED_AT,
            dependencies={
                DependencyName.DATABASE: DependencyReport(
                    state=state, critical=True, latency_ms=LATENCY_MS
                )
            },
        )


def _client(status: HealthStatus) -> TestClient:
    app = FastAPI()
    register_routes(app=app)
    app.dependency_overrides[get_health_service] = lambda: StubHealthService(status=status)
    return TestClient(app)


def test_health_answers_200_with_camel_case_fields_when_the_service_is_ok() -> None:
    # Arrange
    client = _client(status=HealthStatus.OK)

    # Act
    response = client.get(url="/api/v1/health")

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == HealthStatus.OK
    assert body["checkedAt"].startswith("2026-11-12T12:00:00")
    assert body["dependencies"][DependencyName.DATABASE]["latencyMs"] == LATENCY_MS


def test_health_stays_200_when_the_service_is_degraded() -> None:
    # Arrange
    client = _client(status=HealthStatus.DEGRADED)

    # Act
    response = client.get(url="/api/v1/health")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == HealthStatus.DEGRADED


def test_health_answers_503_with_the_report_when_a_critical_dependency_is_down() -> None:
    # Arrange
    client = _client(status=HealthStatus.DOWN)

    # Act
    response = client.get(url="/api/v1/health")

    # Assert
    assert response.status_code == 503
    assert response.json()["dependencies"][DependencyName.DATABASE]["state"] == DependencyState.DOWN


def test_liveness_never_touches_the_dependencies() -> None:
    # Arrange
    app = FastAPI()
    register_routes(app=app)
    client = TestClient(app)

    # Act
    response = client.get(url="/api/v1/health/live")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": HealthStatus.OK}
