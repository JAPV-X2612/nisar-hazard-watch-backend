import httpx
import pytest

from nisar_hazard_watch.adapters.gateway.gateway_case_catalog import GatewayCaseCatalog
from nisar_hazard_watch.config.settings import DEFAULT_ML_GATEWAY_URL
from tests.honesty import forbidden_keys

pytestmark = pytest.mark.live

CLIENT_TIMEOUT_SECONDS = 60.0
# Included, not equal: a new case on the gateway must not break this check.
KNOWN_CASE_IDS = {"chokwe", "qadirabad", "richmond", "kumamoto", "choco", "san-marcos"}


async def test_the_deployed_gateway_serves_the_known_cases_without_unvalidated_values() -> None:
    # Arrange
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        catalog = GatewayCaseCatalog(client=client, base_url=DEFAULT_ML_GATEWAY_URL)

        # Act
        cases = await catalog.cases()

    # Assert
    assert {case.id for case in cases} >= KNOWN_CASE_IDS
    for case in cases:
        assert forbidden_keys(case.model_dump(mode="json")) == []
        assert case.limitations
        assert all(layer.url.startswith(DEFAULT_ML_GATEWAY_URL) for layer in case.layers)
