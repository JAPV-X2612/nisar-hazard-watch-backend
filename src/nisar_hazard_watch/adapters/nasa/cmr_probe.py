import logging
import time

import httpx

from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from nisar_hazard_watch.models.health import DependencyReport
from nisar_hazard_watch.utils.timing import elapsed_ms

logger = logging.getLogger(__name__)

COMPONENT_OK_KEY = "ok?"


class CmrProbe:
    name = DependencyName.CMR
    critical = False

    def __init__(self, client: httpx.AsyncClient, health_url: str) -> None:
        self._client = client
        self._health_url = health_url

    async def check(self) -> DependencyReport:
        started = time.perf_counter()
        try:
            response = await self._client.get(self._health_url)
            response.raise_for_status()
            components = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("NASA CMR health check failed", exc_info=True)
            return DependencyReport(
                state=DependencyState.DOWN,
                critical=self.critical,
                detail="NASA CMR is unreachable",
            )
        failing = sorted(
            name
            for name, status in components.items()
            if isinstance(status, dict) and status.get(COMPONENT_OK_KEY) is False
        )
        if failing:
            return DependencyReport(
                state=DependencyState.DOWN,
                critical=self.critical,
                detail=f"failing components: {', '.join(failing)}",
                latency_ms=elapsed_ms(started),
            )
        return DependencyReport(
            state=DependencyState.OK,
            critical=self.critical,
            latency_ms=elapsed_ms(started),
        )
