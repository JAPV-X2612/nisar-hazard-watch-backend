from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from nisar_hazard_watch.constants.explorations import ExplorationStatus, Lens, SourceBand, Stage
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.exploration import ExplorationResult, ProblemInfo
from nisar_hazard_watch.models.scene import ScenePlan


class ExplorationJob(CamelModel):
    id: str
    status: ExplorationStatus
    stage: Stage
    lens: Lens
    source: SourceBand
    optical_evidence: bool
    cache_key: str
    area_bucket: str
    scenes_total: int
    plan_seconds: float
    plan: ScenePlan | None = None
    runner_id: str | None = None
    result: ExplorationResult | None = None
    error: ProblemInfo | None = None
    layer_urls: dict[str, str] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    finished_at: datetime | None = None
    deadline_at: datetime


class JobRepository(Protocol):
    async def add(self, job: ExplorationJob) -> None: ...

    async def get(self, job_id: str) -> ExplorationJob | None: ...

    async def transition(self, job: ExplorationJob) -> bool:
        """Save the job only while it is still active; False when another writer finished it."""
        ...

    async def expire_overdue(self, now: datetime, error: ProblemInfo) -> int:
        """Close active jobs past their deadline as partial; returns how many."""
        ...

    async def count_active(self, now: datetime) -> int: ...

    async def find_fresh(self, cache_key: str, newer_than: datetime) -> ExplorationJob | None: ...

    async def recent_totals(
        self, lens: Lens, scenes_total: int, area_bucket: str, limit: int
    ) -> list[float]: ...
