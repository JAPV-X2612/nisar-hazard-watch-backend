from typing import Any, Protocol

from nisar_hazard_watch.constants.explorations import Lens, RunnerState
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.scene import ScenePlan


class RunnerJob(CamelModel):
    lens: Lens
    plan: ScenePlan
    optical_evidence: bool = False


class RunnerLayer(CamelModel):
    id: str
    title: str
    kind: str
    units: str
    colormap: str
    bounds: tuple[float, float, float, float]
    url: str
    legend: dict[str, str] | None = None
    value_range: tuple[float, float] | None = None


class RunnerResult(CamelModel):
    science_status: str
    lens: dict[str, Any] | None
    observations: list[dict[str, Any]]
    aoi_summary: dict[str, Any] | None
    layers: list[RunnerLayer]
    quality: dict[str, Any]
    timings: dict[str, float]
    is_demo: bool = False


class RunnerTicket(CamelModel):
    run_id: str
    state: RunnerState
    cached: bool = False
    result: RunnerResult | None = None
    error_code: str | None = None


class AnalysisRunner(Protocol):
    async def submit(self, job: RunnerJob) -> RunnerTicket: ...

    async def poll(self, run_id: str) -> RunnerTicket: ...
