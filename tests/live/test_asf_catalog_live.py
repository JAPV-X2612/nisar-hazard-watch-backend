import itertools
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.constants.sar import PlanStatus
from nisar_hazard_watch.services.scene_planner import ScenePlanner
from tests.factories import qadirabad_aoi

pytestmark = pytest.mark.live

CLIENT_TIMEOUT_SECONDS = 60.0
MAX_AGE_DAYS = 60
MAX_IMAGES = 5


async def test_the_real_asf_catalog_yields_a_ready_plan_for_qadirabad() -> None:
    # Arrange
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        planner = ScenePlanner(catalog=AsfCatalog(client=client))

        # Act
        plan = await planner.plan(aoi=qadirabad_aoi())

    # Assert
    dates = [scene.acquired_at for scene in plan.scenes]
    gaps = [(later - earlier).days for earlier, later in itertools.pairwise(dates)]
    assert plan.status is PlanStatus.READY
    assert len(plan.scenes) <= MAX_IMAGES
    assert datetime.now(UTC) - dates[-1] < timedelta(days=MAX_AGE_DAYS)
    assert all(24 <= gap <= 36 for gap in gaps)
    assert len({(scene.track, scene.direction, scene.frame) for scene in plan.scenes}) == 1
