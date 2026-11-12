import httpx
import pytest

from nisar_hazard_watch.adapters.nasa.cmr_probe import CmrProbe
from nisar_hazard_watch.config.settings import DEFAULT_CMR_HEALTH_URL
from nisar_hazard_watch.constants.health import DependencyState

pytestmark = pytest.mark.live

CLIENT_TIMEOUT_SECONDS = 10.0


async def test_the_real_nasa_cmr_answers_its_health_endpoint() -> None:
    # Arrange
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        probe = CmrProbe(client=client, health_url=DEFAULT_CMR_HEALTH_URL)

        # Act
        report = await probe.check()

    # Assert
    assert report.state is DependencyState.OK
