from datetime import UTC, datetime

from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.models.health import DependencyReport
from nisar_hazard_watch.services.health_service import HealthService

FIXED_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


class FakeProbe:
    def __init__(
        self,
        name: DependencyName,
        critical: bool,
        state: DependencyState,
        *,
        raises: bool = False,
    ) -> None:
        self.name = name
        self.critical = critical
        self._state = state
        self._raises = raises

    async def check(self) -> DependencyReport:
        if self._raises:
            raise RuntimeError("probe exploded")
        return DependencyReport(state=self._state, critical=self.critical)


def _service(*probes: FakeProbe) -> HealthService:
    return HealthService(
        probes=probes,
        service_name="nisar-hazard-watch-backend",
        version="1.2.3",
        environment=Environment.TEST,
        clock=lambda: FIXED_NOW,
    )


async def test_everything_up_is_ok_and_carries_the_service_identity() -> None:
    # Arrange
    service = _service(
        FakeProbe(DependencyName.DATABASE, True, DependencyState.OK),
        FakeProbe(DependencyName.MODAL, False, DependencyState.NOT_CONFIGURED),
    )

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.OK
    assert report.service == "nisar-hazard-watch-backend"
    assert report.version == "1.2.3"
    assert report.environment is Environment.TEST
    assert report.checked_at == FIXED_NOW
    assert set(report.dependencies) == {DependencyName.DATABASE, DependencyName.MODAL}


async def test_a_down_optional_dependency_degrades_the_service() -> None:
    # Arrange
    service = _service(
        FakeProbe(DependencyName.DATABASE, True, DependencyState.OK),
        FakeProbe(DependencyName.CMR, False, DependencyState.DOWN),
    )

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DEGRADED


async def test_a_down_critical_dependency_takes_the_service_down() -> None:
    # Arrange
    service = _service(
        FakeProbe(DependencyName.DATABASE, True, DependencyState.DOWN),
        FakeProbe(DependencyName.CMR, False, DependencyState.OK),
    )

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DOWN


async def test_a_probe_that_raises_is_reported_as_down_instead_of_failing_the_check() -> None:
    # Arrange
    service = _service(FakeProbe(DependencyName.DATABASE, True, DependencyState.OK, raises=True))

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DOWN
    assert report.dependencies[DependencyName.DATABASE].detail == "health probe failed unexpectedly"
