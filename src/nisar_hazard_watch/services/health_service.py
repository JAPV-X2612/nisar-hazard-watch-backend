import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.models.health import DependencyReport, HealthResponse
from nisar_hazard_watch.ports.dependency_probe import DependencyProbe

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _overall_status(dependencies: dict[DependencyName, DependencyReport]) -> HealthStatus:
    down = [report for report in dependencies.values() if report.state is DependencyState.DOWN]
    if any(report.critical for report in down):
        return HealthStatus.DOWN
    return HealthStatus.DEGRADED if down else HealthStatus.OK


class HealthService:
    def __init__(
        self,
        probes: Sequence[DependencyProbe],
        service_name: str,
        version: str,
        environment: Environment,
        probe_timeout_seconds: float,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._probes = list(probes)
        self._service_name = service_name
        self._version = version
        self._environment = environment
        self._probe_timeout_seconds = probe_timeout_seconds
        self._clock = clock

    async def check(self) -> HealthResponse:
        reports = await asyncio.gather(*(self._run(probe=probe) for probe in self._probes))
        dependencies = {
            probe.name: report for probe, report in zip(self._probes, reports, strict=True)
        }
        return HealthResponse(
            status=_overall_status(dependencies=dependencies),
            service=self._service_name,
            version=self._version,
            environment=self._environment,
            checked_at=self._clock(),
            dependencies=dependencies,
        )

    async def _run(self, probe: DependencyProbe) -> DependencyReport:
        try:
            async with asyncio.timeout(self._probe_timeout_seconds):
                return await probe.check()
        except TimeoutError:
            logger.warning("health probe %s timed out", probe.name)
            return self._down(probe=probe, detail="health probe timed out")
        except Exception:
            logger.exception("health probe %s raised", probe.name)
            return self._down(probe=probe, detail="health probe failed unexpectedly")

    @staticmethod
    def _down(probe: DependencyProbe, detail: str) -> DependencyReport:
        return DependencyReport(state=DependencyState.DOWN, critical=probe.critical, detail=detail)
