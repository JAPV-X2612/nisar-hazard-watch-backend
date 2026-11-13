import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from nisar_hazard_watch.adapters.firms.firms_client import FirmsClient
from nisar_hazard_watch.config.settings import DEFAULT_FIRMS_URL

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("FIRMS_MAP_KEY"), reason="FIRMS_MAP_KEY is not set"),
]

CLIENT_TIMEOUT_SECONDS = 30.0
SAVANNA_BOX = (20.0, 6.0, 26.0, 10.0)
WINDOW_DAYS = 4
LATEST_AVAILABLE_LAG_DAYS = 2


async def test_the_real_firms_service_serves_detections_over_the_savanna_belt() -> None:
    # Arrange
    end = (datetime.now(UTC) - timedelta(days=LATEST_AVAILABLE_LAG_DAYS)).date()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    key = SecretStr(os.environ["FIRMS_MAP_KEY"])
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        source = FirmsClient(client=client, base_url=DEFAULT_FIRMS_URL, map_key=key)

        # Act
        search = await source.search(bbox=SAVANNA_BOX, start=start, end=end)

    # Assert
    assert search.products
    assert search.detections
    assert all(detection.confidence for detection in search.detections)
