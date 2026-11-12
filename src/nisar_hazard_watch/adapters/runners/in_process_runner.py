import itertools
import time
from collections.abc import Callable

from nisar_hazard_watch.constants.explorations import OBSERVED_STATUS, LayerKind, RunnerState
from nisar_hazard_watch.ports.analysis_runner import (
    RunnerJob,
    RunnerLayer,
    RunnerResult,
    RunnerTicket,
)

SYNTHETIC_LAYER_URL = "https://runner.invalid/synthetic.png"


class InProcessRunner:
    """Deterministic stand-in for tests and local runs. Its numbers are synthetic, never science."""

    def __init__(
        self,
        duration_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        fail_with: str | None = None,
    ) -> None:
        self._duration_seconds = duration_seconds
        self._clock = clock
        self._fail_with = fail_with
        self._counter = itertools.count(1)
        self._runs: dict[str, tuple[float, RunnerJob]] = {}

    async def submit(self, job: RunnerJob) -> RunnerTicket:
        run_id = f"local-{next(self._counter)}"
        self._runs[run_id] = (self._clock(), job)
        return await self.poll(run_id=run_id)

    async def poll(self, run_id: str) -> RunnerTicket:
        started, job = self._runs[run_id]
        if self._clock() - started < self._duration_seconds:
            return RunnerTicket(run_id=run_id, state=RunnerState.RUNNING)
        if self._fail_with:
            return RunnerTicket(run_id=run_id, state=RunnerState.FAILED, error_code=self._fail_with)
        return RunnerTicket(run_id=run_id, state=RunnerState.SUCCEEDED, result=self._result(job))

    @staticmethod
    def _result(job: RunnerJob) -> RunnerResult:
        west, south, east, north = job.plan.aoi.bbox
        return RunnerResult(
            science_status="complete",
            lens={"status": "evaluated", "synthetic": True},
            observations=[
                {"date": f"{scene.acquired_at:%Y-%m-%d}", "status": OBSERVED_STATUS}
                for scene in job.plan.scenes
            ],
            aoi_summary=None,
            layers=[
                RunnerLayer(
                    id="display_synthetic",
                    title="synthetic",
                    kind=LayerKind.OBSERVED.value,
                    units="dB",
                    colormap="gray",
                    bounds=(west, south, east, north),
                    url=SYNTHETIC_LAYER_URL,
                )
            ],
            quality={"synthetic": True},
            timings={"elapsed_s": 0.0},
            is_demo=True,
        )
