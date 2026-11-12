import asyncio
from datetime import UTC, datetime

from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.models.health import DependencyReport
from nisar_hazard_watch.services.health_service import HealthService
from tests.constants import SERVICE_NAME, SERVICE_VERSION

FIXED_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
PROBE_TIMEOUT_SECONDS = 0.05
HANG_SECONDS = 10


class FakeProbe:
    def __init__(
        self,
        name: DependencyName,
        critical: bool,
        state: DependencyState,
        raises: bool = False,
        hangs: bool = False,
    ) -> None:
        self.name = name
        self.critical = critical
        self._state = state
        self._raises = raises
        self._hangs = hangs

    async def check(self) -> DependencyReport:
        if self._raises:
            raise RuntimeError("probe exploded")
        if self._hangs:
            await asyncio.sleep(HANG_SECONDS)
        return DependencyReport(state=self._state, critical=self.critical)


def _service(probes: list[FakeProbe]) -> HealthService:
    return HealthService(
        probes=probes,
        service_name=SERVICE_NAME,
        version=SERVICE_VERSION,
        environment=Environment.TEST,
        probe_timeout_seconds=PROBE_TIMEOUT_SECONDS,
        clock=lambda: FIXED_NOW,
    )


async def test_everything_up_is_ok_and_carries_the_service_identity() -> None:
    # Arrange
    database = FakeProbe(name=DependencyName.DATABASE, critical=True, state=DependencyState.OK)
    modal = FakeProbe(
        name=DependencyName.MODAL, critical=False, state=DependencyState.NOT_CONFIGURED
    )
    service = _service(probes=[database, modal])

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.OK
    assert report.service == SERVICE_NAME
    assert report.version == SERVICE_VERSION
    assert report.environment is Environment.TEST
    assert report.checked_at == FIXED_NOW
    assert set(report.dependencies) == {DependencyName.DATABASE, DependencyName.MODAL}


async def test_a_down_optional_dependency_degrades_the_service() -> None:
    # Arrange
    database = FakeProbe(name=DependencyName.DATABASE, critical=True, state=DependencyState.OK)
    cmr = FakeProbe(name=DependencyName.CMR, critical=False, state=DependencyState.DOWN)
    service = _service(probes=[database, cmr])

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DEGRADED


async def test_a_down_critical_dependency_takes_the_service_down() -> None:
    # Arrange
    database = FakeProbe(name=DependencyName.DATABASE, critical=True, state=DependencyState.DOWN)
    cmr = FakeProbe(name=DependencyName.CMR, critical=False, state=DependencyState.OK)
    service = _service(probes=[database, cmr])

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DOWN


async def test_a_probe_that_raises_is_reported_as_down_instead_of_failing_the_check() -> None:
    # Arrange
    database = FakeProbe(
        name=DependencyName.DATABASE,
        critical=True,
        state=DependencyState.OK,
        raises=True,
    )
    service = _service(probes=[database])

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DOWN
    assert report.dependencies[DependencyName.DATABASE].detail == "health probe failed unexpectedly"


async def test_a_probe_that_hangs_is_cut_off_and_reported_as_down() -> None:
    # Arrange
    cmr = FakeProbe(name=DependencyName.CMR, critical=False, state=DependencyState.OK, hangs=True)
    service = _service(probes=[cmr])

    # Act
    report = await service.check()

    # Assert
    assert report.status is HealthStatus.DEGRADED
    assert report.dependencies[DependencyName.CMR].state is DependencyState.DOWN
    assert report.dependencies[DependencyName.CMR].detail == "health probe timed out"
