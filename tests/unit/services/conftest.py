from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nisar_hazard_watch.adapters.cases.static_precomputed_cases import StaticPrecomputedCases
from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
from nisar_hazard_watch.adapters.db.models import Base
from nisar_hazard_watch.constants.fire_context import FireContextStatus
from nisar_hazard_watch.models.fire_context import FireContext
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import ScenePlan
from nisar_hazard_watch.ports.analysis_runner import (
    RunnerJob,
    RunnerResult,
    RunnerState,
    RunnerTicket,
)
from nisar_hazard_watch.ports.fire_context_provider import FireContextProvider
from nisar_hazard_watch.ports.precomputed_cases import PrecomputedCases
from nisar_hazard_watch.services.eta_estimator import EtaEstimator
from nisar_hazard_watch.services.exploration_service import ExplorationService
from tests.factories import make_plan

START = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
MAX_ACTIVE = 2
DEADLINE_SECONDS = 55.0
CACHE_TTL_SECONDS = 86400.0
PRIOR_SECONDS = 60.0


class ManualClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakePlanner:
    def __init__(self, plan: ScenePlan | Exception | None = None) -> None:
        self.plan_result: ScenePlan | Exception = plan or make_plan()
        self.calls = 0

    async def plan(self, aoi: Aoi) -> ScenePlan:
        self.calls += 1
        if isinstance(self.plan_result, Exception):
            raise self.plan_result
        return self.plan_result.model_copy(update={"aoi": aoi})


class ScriptedRunner:
    """Answers submit and poll from a script; counts what the service asked for."""

    def __init__(self) -> None:
        self.submissions: list[RunnerJob] = []
        self.submit_ticket = RunnerTicket(run_id="run-1", state=RunnerState.RUNNING)
        self.poll_ticket: RunnerTicket | Exception = self.submit_ticket
        self.while_polling: Callable[[], Awaitable[None]] | None = None

    async def submit(self, job: RunnerJob) -> RunnerTicket:
        self.submissions.append(job)
        return self.submit_ticket

    async def poll(self, run_id: str) -> RunnerTicket:
        if self.while_polling is not None:
            await self.while_polling()
        if isinstance(self.poll_ticket, Exception):
            raise self.poll_ticket
        return self.poll_ticket


class FakeFireContext:
    """Returns the next scripted context and counts the plans it was asked about."""

    def __init__(self, *contexts: FireContext) -> None:
        self.contexts = list(contexts) or [
            FireContext(status=FireContextStatus.AVAILABLE, note="n")
        ]
        self.plans: list[ScenePlan] = []

    async def fire_context(self, plan: ScenePlan) -> FireContext:
        self.plans.append(plan)
        return self.contexts.pop(0) if len(self.contexts) > 1 else self.contexts[0]


def runner_result(**overrides: object) -> RunnerResult:
    values: dict[str, object] = {
        "science_status": "complete",
        "lens": {"status": "evaluated"},
        "observations": [{"date": f"2026-0{i}-01", "status": "observed"} for i in range(5, 10)],
        "aoi_summary": {"cells_in_area": 100},
        "layers": [],
        "quality": {"gridWidth": 1024},
        "timings": {"prefetch_s": 4.0, "measure_s": 10.0, "render_s": 15.0, "elapsed_s": 35.0},
        **overrides,
    }
    return RunnerResult(**values)  # type: ignore[arg-type]


@pytest.fixture
async def repository(tmp_path: Path) -> AsyncIterator[SqlJobRepository]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield SqlJobRepository(session_factory=async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def planner() -> FakePlanner:
    return FakePlanner()


@pytest.fixture
def runner() -> ScriptedRunner:
    return ScriptedRunner()


@pytest.fixture
def make_service(
    repository: SqlJobRepository, clock: ManualClock, planner: FakePlanner, runner: ScriptedRunner
) -> Callable[..., ExplorationService]:
    def build(
        cases: PrecomputedCases | None = None,
        max_active: int = MAX_ACTIVE,
        fire_context: FireContextProvider | None = None,
    ) -> ExplorationService:
        return ExplorationService(
            planner=planner,  # type: ignore[arg-type]
            runner=runner,
            repository=repository,
            eta=EtaEstimator(repository=repository, prior_seconds=PRIOR_SECONDS),
            cases=cases or StaticPrecomputedCases(cases=[]),
            max_active=max_active,
            deadline_seconds=DEADLINE_SECONDS,
            cache_ttl_seconds=CACHE_TTL_SECONDS,
            fire_context=fire_context,
            clock=clock,
        )

    return build
