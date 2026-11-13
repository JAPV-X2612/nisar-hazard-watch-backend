from nisar_hazard_watch.utils.ttl_cache import TtlCache

MAX_ENTRIES = 2
TTL_SECONDS = 10.0


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_stored_value_is_returned_until_it_expires() -> None:
    # Arrange
    clock = ManualClock()
    cache = TtlCache[str](max_entries=MAX_ENTRIES, clock=clock)
    cache.put(key="a", value="alpha", ttl_seconds=TTL_SECONDS)

    # Act
    before = cache.get(key="a")
    clock.now = TTL_SECONDS
    after = cache.get(key="a")

    # Assert
    assert before == "alpha"
    assert after is None


def test_an_unknown_key_is_none() -> None:
    # Arrange
    cache = TtlCache[str](max_entries=MAX_ENTRIES)

    # Act
    value = cache.get(key="missing")

    # Assert
    assert value is None


def test_the_least_recently_used_entry_leaves_first() -> None:
    # Arrange
    cache = TtlCache[str](max_entries=MAX_ENTRIES)
    cache.put(key="a", value="alpha", ttl_seconds=TTL_SECONDS)
    cache.put(key="b", value="beta", ttl_seconds=TTL_SECONDS)
    cache.get(key="a")

    # Act
    cache.put(key="c", value="gamma", ttl_seconds=TTL_SECONDS)

    # Assert
    assert cache.get(key="a") == "alpha"
    assert cache.get(key="b") is None
    assert cache.get(key="c") == "gamma"


def test_putting_a_key_again_replaces_its_value_and_its_lifetime() -> None:
    # Arrange
    clock = ManualClock()
    cache = TtlCache[str](max_entries=MAX_ENTRIES, clock=clock)
    cache.put(key="a", value="old", ttl_seconds=TTL_SECONDS)
    clock.now = TTL_SECONDS - 1

    # Act
    cache.put(key="a", value="new", ttl_seconds=TTL_SECONDS)
    clock.now = TTL_SECONDS + 1

    # Assert
    assert cache.get(key="a") == "new"
