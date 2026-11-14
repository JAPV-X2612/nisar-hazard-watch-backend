import asyncio
import logging
import time
from collections.abc import Callable

from nisar_hazard_watch.constants.cases import CASES_UNAVAILABLE_DETAIL
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

    A stale copy beats an outage: the cases were measured ahead of time and stay true. Once a
    copy exists, callers get it at once and an expired copy is refreshed in the background, so
    nobody waits on the gateway. After a failed read the gateway is not called again for a while.
    """

    def __init__(
        self,
        catalog: CaseCatalog,
        ttl_seconds: float,
        retry_after_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._catalog = catalog
        self._ttl_seconds = ttl_seconds
        self._retry_after_seconds = retry_after_seconds
        self._clock = clock
        self._cases: list[CaseView] | None = None
        self._fetched_at = 0.0
        self._retry_at = 0.0
        self._refresh: asyncio.Task[None] | None = None
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
        if self._cases is not None:
            if self._is_due() and (self._refresh is None or self._refresh.done()):
                self._refresh = asyncio.create_task(self._refresh_in_background())
            return self._cases
        async with self._lock:
            if self._cases is not None:
                return self._cases
            if self._clock() < self._retry_at:
                raise CasesUnavailableError(CASES_UNAVAILABLE_DETAIL)
            return await self._read()

    def _is_due(self) -> bool:
        now = self._clock()
        return now - self._fetched_at >= self._ttl_seconds and now >= self._retry_at

    async def _read(self) -> list[CaseView]:
        try:
            cases = await self._catalog.cases()
        except CasesUnavailableError:
            self._retry_at = self._clock() + self._retry_after_seconds
            raise
        self._cases = cases
        self._fetched_at = self._clock()
        return cases

    async def _refresh_in_background(self) -> None:
        try:
            await self._read()
        except CasesUnavailableError:
            logger.warning("known cases unavailable; serving the cached copy")
