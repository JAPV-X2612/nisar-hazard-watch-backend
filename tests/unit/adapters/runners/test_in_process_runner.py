from nisar_hazard_watch.adapters.runners.in_process_runner import InProcessRunner
from nisar_hazard_watch.constants.explorations import Lens, RunnerState
from nisar_hazard_watch.ports.analysis_runner import RunnerJob
from tests.factories import make_plan


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _job() -> RunnerJob:
    return RunnerJob(lens=Lens.FLOOD_WETLAND, plan=make_plan())


async def test_a_job_runs_until_its_duration_has_passed() -> None:
    # Arrange
    clock = ManualClock()
    runner = InProcessRunner(duration_seconds=10, clock=clock)

    # Act
    submitted = await runner.submit(job=_job())
    clock.now = 9.0
    still_running = await runner.poll(run_id=submitted.run_id)
    clock.now = 10.0
    finished = await runner.poll(run_id=submitted.run_id)

    # Assert
    assert submitted.state is RunnerState.RUNNING
    assert still_running.state is RunnerState.RUNNING
    assert finished.state is RunnerState.SUCCEEDED


async def test_the_synthetic_result_is_always_labelled_as_demo() -> None:
    # Arrange
    runner = InProcessRunner()

    # Act
    ticket = await runner.submit(job=_job())

    # Assert
    assert ticket.state is RunnerState.SUCCEEDED
    assert ticket.result is not None
    assert ticket.result.is_demo is True
    assert ticket.result.lens == {"status": "evaluated", "synthetic": True}
    assert len(ticket.result.observations) == 5


async def test_a_runner_can_be_told_to_fail() -> None:
    # Arrange
    runner = InProcessRunner(fail_with="worker_failed")

    # Act
    ticket = await runner.submit(job=_job())

    # Assert
    assert ticket.state is RunnerState.FAILED
    assert ticket.error_code == "worker_failed"
