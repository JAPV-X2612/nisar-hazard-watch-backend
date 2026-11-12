import asyncio
import time

import httpx
import pytest

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.adapters.runners.gateway_runner import GatewayRunner
from nisar_hazard_watch.config.settings import DEFAULT_ML_GATEWAY_URL
from nisar_hazard_watch.constants.explorations import Lens, RunnerState
from nisar_hazard_watch.ports.analysis_runner import RunnerJob
from nisar_hazard_watch.services.scene_planner import ScenePlanner
from tests.factories import qadirabad_aoi

pytestmark = pytest.mark.live

CLIENT_TIMEOUT_SECONDS = 60.0
MAX_WAIT_SECONDS = 180.0
POLL_SECONDS = 4.0


async def test_the_real_plan_runs_on_the_deployed_ml_gateway() -> None:
    # Arrange
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        plan = await ScenePlanner(catalog=AsfCatalog(client=client)).plan(aoi=qadirabad_aoi())
        runner = GatewayRunner(client=client, base_url=DEFAULT_ML_GATEWAY_URL)
        job = RunnerJob(lens=Lens.FLOOD_WETLAND, plan=plan)

        # Act
        ticket = await runner.submit(job=job)
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while ticket.state in (RunnerState.QUEUED, RunnerState.RUNNING):
            assert time.monotonic() < deadline, "the exploration did not finish in time"
            await asyncio.sleep(POLL_SECONDS)
            ticket = await runner.poll(run_id=ticket.run_id)

    # Assert
    assert ticket.state is RunnerState.SUCCEEDED
    assert ticket.result is not None
    assert ticket.result.science_status == "complete"
    assert ticket.result.lens is not None
    assert ticket.result.lens["status"] == "evaluated"
    assert ticket.result.aoi_summary is not None
    assert ticket.result.aoi_summary["cells_with_measurement"] > 1_000_000
    assert ticket.result.layers
