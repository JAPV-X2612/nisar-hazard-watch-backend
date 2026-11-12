import pytest

from nisar_hazard_watch.constants.places import (
    CACHE_TTL_SECONDS,
    EMPTY_CACHE_TTL_SECONDS,
    MAX_QUERY_LENGTH,
    PLACES_ATTRIBUTION,
    PROVIDER_MIN_INTERVAL_SECONDS,
)
from nisar_hazard_watch.exceptions.exploration_errors import QueueFullError
from nisar_hazard_watch.exceptions.place_errors import GeocoderUnavailableError, InvalidQueryError
from nisar_hazard_watch.models.place import PlaceView
from nisar_hazard_watch.ports.geocoder import Geocoder
from nisar_hazard_watch.services.place_search_service import PlaceSearchService
from nisar_hazard_watch.utils.min_interval_throttle import MinIntervalThrottle
from nisar_hazard_watch.utils.ttl_cache import TtlCache

LIMIT = 6
QUADIRABAD = PlaceView(
    id="n4295615569",
    name="Qadirabad",
    display_name="Qadirabad, Punjab, Pakistan",
    kind="town",
    point=(73.5025289, 32.297263),
    bbox=(73.4625289, 32.257263, 73.5425289, 32.337263),
    importance=0.16,
)


class ManualClock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeGeocoder:
    def __init__(self, places: list[PlaceView] | Exception) -> None:
        self.places = places
        self.queries: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int) -> list[PlaceView]:
        self.queries.append((query, limit))
        if isinstance(self.places, Exception):
            raise self.places
        return self.places


def _service(
    geocoder: FakeGeocoder, clock: ManualClock | None = None
) -> tuple[PlaceSearchService, ManualClock]:
    clock = clock or ManualClock()
    service = PlaceSearchService(
        geocoder=geocoder,
        cache=TtlCache[list[PlaceView]](max_entries=16, clock=clock),
        throttle=MinIntervalThrottle(
            min_interval_seconds=PROVIDER_MIN_INTERVAL_SECONDS, clock=clock, sleep=clock.sleep
        ),
    )
    return service, clock


async def test_a_search_returns_the_places_with_their_attribution() -> None:
    # Arrange
    service, _ = _service(geocoder=FakeGeocoder(places=[QUADIRABAD]))

    # Act
    view = await service.search(query="Qadirabad", limit=LIMIT)

    # Assert
    assert view.places == [QUADIRABAD]
    assert view.attribution == PLACES_ATTRIBUTION


async def test_the_same_text_in_any_case_or_spacing_asks_the_provider_once() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    service, _ = _service(geocoder=geocoder)

    # Act
    await service.search(query="Qadirabad", limit=LIMIT)
    await service.search(query="  QADIRABAD ", limit=LIMIT)
    await service.search(query="qadirabad", limit=LIMIT)

    # Assert
    assert geocoder.queries == [("Qadirabad", LIMIT)]


async def test_the_provider_receives_the_trimmed_text_with_single_spaces() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    service, _ = _service(geocoder=geocoder)

    # Act
    await service.search(query="  Rio   Cauca ", limit=LIMIT)

    # Assert
    assert geocoder.queries == [("Rio Cauca", LIMIT)]


async def test_a_different_limit_is_a_different_search() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    service, _ = _service(geocoder=geocoder)

    # Act
    await service.search(query="Qadirabad", limit=3)
    await service.search(query="Qadirabad", limit=LIMIT)

    # Assert
    assert [limit for _, limit in geocoder.queries] == [3, LIMIT]


async def test_an_entry_expires_after_a_day() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    service, clock = _service(geocoder=geocoder)
    await service.search(query="Qadirabad", limit=LIMIT)
    clock.now += CACHE_TTL_SECONDS

    # Act
    await service.search(query="Qadirabad", limit=LIMIT)

    # Assert
    assert len(geocoder.queries) == 2


async def test_an_empty_answer_is_remembered_only_for_an_hour() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[])
    service, clock = _service(geocoder=geocoder)

    # Act
    await service.search(query="Nowhereville", limit=LIMIT)
    await service.search(query="Nowhereville", limit=LIMIT)
    clock.now += EMPTY_CACHE_TTL_SECONDS
    await service.search(query="Nowhereville", limit=LIMIT)

    # Assert
    assert len(geocoder.queries) == 2


async def test_distinct_searches_are_spaced_at_the_providers_rate() -> None:
    # Arrange
    service, clock = _service(geocoder=FakeGeocoder(places=[QUADIRABAD]))

    # Act
    await service.search(query="one", limit=LIMIT)
    await service.search(query="two", limit=LIMIT)

    # Assert
    assert clock.slept == [pytest.approx(PROVIDER_MIN_INTERVAL_SECONDS)]


@pytest.mark.parametrize(
    argnames="query",
    argvalues=["", " ", "a", "   x  ", "y" * (MAX_QUERY_LENGTH + 1)],
    ids=["empty", "blank", "one-character", "one-after-trimming", "too-long"],
)
async def test_text_outside_the_allowed_length_is_refused_before_any_call(query: str) -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    service, _ = _service(geocoder=geocoder)

    # Act / Assert
    with pytest.raises(expected_exception=InvalidQueryError):
        await service.search(query=query, limit=LIMIT)
    assert geocoder.queries == []


async def test_a_provider_failure_is_not_cached() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=GeocoderUnavailableError("down"))
    service, _ = _service(geocoder=geocoder)

    # Act
    for _ in range(2):
        with pytest.raises(expected_exception=GeocoderUnavailableError):
            await service.search(query="Qadirabad", limit=LIMIT)

    # Assert
    assert len(geocoder.queries) == 2


async def test_a_queue_longer_than_the_wait_cap_answers_busy_without_calling_the_provider() -> None:
    # Arrange
    geocoder = FakeGeocoder(places=[QUADIRABAD])
    clock = ManualClock()
    service = PlaceSearchService(
        geocoder=geocoder,
        cache=TtlCache[list[PlaceView]](max_entries=16, clock=clock),
        throttle=MinIntervalThrottle(min_interval_seconds=100.0, clock=clock, sleep=clock.sleep),
    )
    await service.search(query="one", limit=LIMIT)

    # Act / Assert
    with pytest.raises(expected_exception=QueueFullError):
        await service.search(query="two", limit=LIMIT)
    assert [query for query, _ in geocoder.queries] == ["one"]


def test_the_fake_geocoder_satisfies_the_port() -> None:
    # Arrange
    geocoder: Geocoder = FakeGeocoder(places=[])

    # Act
    searched = geocoder.search

    # Assert
    assert callable(searched)
