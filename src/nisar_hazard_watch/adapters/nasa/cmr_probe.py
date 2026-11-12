import logging
import time

import httpx

from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from nisar_hazard_watch.models.health import DependencyReport
from nisar_hazard_watch.utils.timing import elapsed_ms

logger = logging.getLogger(__name__)

COMPONENT_OK_KEY = "ok?"
UNREACHABLE_DETAIL = "NASA CMR is unreachable"
UNEXPECTED_RESPONSE_DETAIL = "NASA CMR returned an unexpected health response"


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
            body = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("NASA CMR health check failed", exc_info=True)
            return self._down(detail=UNREACHABLE_DETAIL)

        components = self._components(body=body)
        if not components:
            logger.warning("NASA CMR health response has no recognised components: %r", body)
            return self._down(detail=UNEXPECTED_RESPONSE_DETAIL)

        failing = sorted(name for name, healthy in components.items() if not healthy)
        if failing:
            detail = f"failing components: {', '.join(failing)}"
            logger.warning("NASA CMR reports %s", detail)
            return self._down(detail=detail, latency_ms=elapsed_ms(started=started))
        return DependencyReport(
            state=DependencyState.OK,
            critical=self.critical,
            latency_ms=elapsed_ms(started=started),
        )

    @staticmethod
    def _components(body: object) -> dict[str, bool]:
        if not isinstance(body, dict):
            return {}
        return {
            name: status[COMPONENT_OK_KEY] is True
            for name, status in body.items()
            if isinstance(status, dict) and COMPONENT_OK_KEY in status
        }

    def _down(self, detail: str, latency_ms: float | None = None) -> DependencyReport:
        return DependencyReport(
            state=DependencyState.DOWN,
            critical=self.critical,
            detail=detail,
            latency_ms=latency_ms,
        )
