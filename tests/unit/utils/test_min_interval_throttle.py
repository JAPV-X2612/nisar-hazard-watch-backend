import pytest

from nisar_hazard_watch.utils.min_interval_throttle import MinIntervalThrottle, ThrottleBusyError

INTERVAL_SECONDS = 1.0
MAX_WAIT_SECONDS = 3.0


class ManualClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _throttle(clock: ManualClock) -> MinIntervalThrottle:
    return MinIntervalThrottle(
        min_interval_seconds=INTERVAL_SECONDS, clock=clock, sleep=clock.sleep
    )


async def test_the_first_call_goes_straight_through() -> None:
    # Arrange
    clock = ManualClock()
    throttle = _throttle(clock=clock)

    # Act
    await throttle.wait_turn(max_wait_seconds=MAX_WAIT_SECONDS)

    # Assert
    assert clock.slept == []


async def test_calls_in_a_burst_are_spaced_by_the_interval() -> None:
    # Arrange
    clock = ManualClock()
    throttle = _throttle(clock=clock)

    # Act
    for _ in range(3):
        await throttle.wait_turn(max_wait_seconds=MAX_WAIT_SECONDS)

    # Assert
    assert clock.slept == [INTERVAL_SECONDS, INTERVAL_SECONDS]


async def test_a_call_after_a_pause_does_not_wait() -> None:
    # Arrange
    clock = ManualClock()
    throttle = _throttle(clock=clock)
    await throttle.wait_turn(max_wait_seconds=MAX_WAIT_SECONDS)
    clock.now += 5 * INTERVAL_SECONDS

    # Act
    await throttle.wait_turn(max_wait_seconds=MAX_WAIT_SECONDS)

    # Assert
    assert clock.slept == []


async def test_a_slot_further_away_than_the_caller_will_wait_is_refused_and_not_reserved() -> None:
    # Arrange
    clock = ManualClock()
    throttle = _throttle(clock=clock)
    for _ in range(4):
        await throttle.wait_turn(max_wait_seconds=MAX_WAIT_SECONDS)
    clock.now -= 3 * INTERVAL_SECONDS
    slept_before = len(clock.slept)

    # Act / Assert
    with pytest.raises(expected_exception=ThrottleBusyError):
        await throttle.wait_turn(max_wait_seconds=0.5)
    assert len(clock.slept) == slept_before
