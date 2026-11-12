from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from nisar_hazard_watch.constants.insar import PAIR_WINDOW_DEFAULT_DAYS, PAIR_WINDOW_MAX_DAYS
from nisar_hazard_watch.exceptions.pair_errors import InvalidPairWindowError
from nisar_hazard_watch.models.insar_pairs import InsarPairsView
from nisar_hazard_watch.ports.insar_pair_catalog import InsarPairCatalog


def _today() -> date:
    return datetime.now(UTC).date()


class InsarPairsService:
    """Lists the interferometric pairs a point can be asked about, newest first."""

    def __init__(self, catalog: InsarPairCatalog, today: Callable[[], date] = _today) -> None:
        self._catalog = catalog
        self._today = today

    async def pairs(
        self, longitude: float, latitude: float, start: date | None, end: date | None
    ) -> InsarPairsView:
        window_end = end or self._today()
        window_start = start or window_end - timedelta(days=PAIR_WINDOW_DEFAULT_DAYS)
        if not 0 < (window_end - window_start).days <= PAIR_WINDOW_MAX_DAYS:
            raise InvalidPairWindowError(
                f"use an increasing window of at most {PAIR_WINDOW_MAX_DAYS} days"
            )
        pairs = await self._catalog.pairs(
            longitude=longitude, latitude=latitude, start=window_start, end=window_end
        )
        return InsarPairsView(window_start=window_start, window_end=window_end, pairs=pairs)
