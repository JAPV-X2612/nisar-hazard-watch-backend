import asyncio
import logging
import time
from collections.abc import Callable

from nisar_hazard_watch.constants.routes import API_PREFIX, CASES_PREFIX
from nisar_hazard_watch.exceptions.case_errors import (
    CaseLayerNotFoundError,
    CaseNotFoundError,
    CasesUnavailableError,
)
from nisar_hazard_watch.models.case import CaseSummary, CasesView, CaseView
from nisar_hazard_watch.ports.case_catalog import CaseCatalog

logger = logging.getLogger(__name__)


class CaseService:
    """Relays the known cases, kept in memory because they rarely change.

    A stale copy beats an outage: the cases were measured ahead of time and stay true.
    """

    def __init__(
        self,
        catalog: CaseCatalog,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._catalog = catalog
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cases: list[CaseView] | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def cases(self) -> CasesView:
        cases = await self._known()
        return CasesView(cases=[CaseSummary.model_validate(case.model_dump()) for case in cases])

    async def get(self, case_id: str) -> CaseView:
        case = await self._find(case_id=case_id)
        prefix = f"{API_PREFIX}{CASES_PREFIX}/{case.id}/layers"
        return case.model_copy(
            update={
                "layers": [
                    layer.model_copy(update={"url": f"{prefix}/{layer.id}"})
                    for layer in case.layers
                ],
                "visualizations": [
                    view.model_copy(update={"url": f"{prefix}/{view.id}"})
                    for view in case.visualizations
                ],
            }
        )

    async def layer_url(self, case_id: str, layer_id: str) -> str:
        case = await self._find(case_id=case_id)
        for image in [*case.layers, *case.visualizations]:
            if image.id == layer_id:
                return image.url
        raise CaseLayerNotFoundError(f"the case has no layer {layer_id!r}")

    async def _find(self, case_id: str) -> CaseView:
        for case in await self._known():
            if case.id == case_id:
                return case
        raise CaseNotFoundError(f"there is no known case {case_id!r}")

    async def _known(self) -> list[CaseView]:
        async with self._lock:
            if self._cases is not None and self._clock() - self._fetched_at < self._ttl_seconds:
                return self._cases
            try:
                self._cases = await self._catalog.cases()
            except CasesUnavailableError:
                if self._cases is None:
                    raise
                logger.warning("known cases unavailable; serving the cached copy")
                return self._cases
            self._fetched_at = self._clock()
            return self._cases
