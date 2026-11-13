import logging

from nisar_hazard_watch.constants.places import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    EMPTY_CACHE_TTL_SECONDS,
    MAX_QUERY_LENGTH,
    MAX_QUEUE_WAIT_SECONDS,
    MIN_QUERY_LENGTH,
    PLACES_ATTRIBUTION,
    PROVIDER_MIN_INTERVAL_SECONDS,
)
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError
from nisar_hazard_watch.exceptions.place_errors import InvalidQueryError
from nisar_hazard_watch.models.place import PlacesView, PlaceView
from nisar_hazard_watch.ports.geocoder import Geocoder
from nisar_hazard_watch.utils.min_interval_throttle import MinIntervalThrottle, ThrottleBusyError
from nisar_hazard_watch.utils.ttl_cache import TtlCache

logger = logging.getLogger(__name__)


def normalise_query(query: str) -> str:
    return " ".join(query.split())


class PlaceSearchService:
    """Looks places up at the provider at most once a second, and once per distinct text."""

    def __init__(
        self,
        geocoder: Geocoder,
        cache: TtlCache[list[PlaceView]] | None = None,
        throttle: MinIntervalThrottle | None = None,
    ) -> None:
        self._geocoder = geocoder
        self._cache = cache or TtlCache(max_entries=CACHE_MAX_ENTRIES)
        self._throttle = throttle or MinIntervalThrottle(
            min_interval_seconds=PROVIDER_MIN_INTERVAL_SECONDS
        )

    async def search(self, query: str, limit: int) -> PlacesView:
        text = normalise_query(query=query)
        if not MIN_QUERY_LENGTH <= len(text) <= MAX_QUERY_LENGTH:
            raise InvalidQueryError(
                f"search for {MIN_QUERY_LENGTH} to {MAX_QUERY_LENGTH} characters"
            )
        key = f"{limit}|{text.casefold()}"
        places = self._cache.get(key=key)
        if places is None:
            places = await self._ask_provider(text=text, limit=limit)
            ttl = CACHE_TTL_SECONDS if places else EMPTY_CACHE_TTL_SECONDS
            self._cache.put(key=key, value=places, ttl_seconds=ttl)
        return PlacesView(places=places, attribution=PLACES_ATTRIBUTION)

    async def _ask_provider(self, text: str, limit: int) -> list[PlaceView]:
        try:
            await self._throttle.wait_turn(max_wait_seconds=MAX_QUEUE_WAIT_SECONDS)
        except ThrottleBusyError as exc:
            logger.warning("place search is busy: %s", exc)
            raise QueueFullError("place search is busy; retry in a few seconds") from exc
        return await self._geocoder.search(query=text, limit=limit)
