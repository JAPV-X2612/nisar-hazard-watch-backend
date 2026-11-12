from datetime import datetime

from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState, HealthStatus
from nisar_hazard_watch.models.base_model import CamelModel


class DependencyReport(CamelModel):
    state: DependencyState
    critical: bool
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(CamelModel):
    status: HealthStatus
    service: str
    version: str
    environment: Environment
    checked_at: datetime
    dependencies: dict[DependencyName, DependencyReport]


class LiveResponse(CamelModel):
    status: HealthStatus = HealthStatus.OK
