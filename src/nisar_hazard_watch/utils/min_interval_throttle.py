import asyncio
import time
from collections.abc import Awaitable, Callable


class ThrottleBusyError(Exception):
    """The next free slot is further away than the caller is willing to wait."""


class MinIntervalThrottle:
    """Spaces the start of calls at least `min_interval_seconds` apart, in arrival order."""

    def __init__(
        self,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._lock = asyncio.Lock()

    async def wait_turn(self, max_wait_seconds: float) -> None:
        async with self._lock:
            now = self._clock()
            start = max(now, self._next_slot)
            wait = start - now
            if wait > max_wait_seconds:
                raise ThrottleBusyError(f"the next free slot is {wait:.1f} s away")
            self._next_slot = start + self._min_interval_seconds
        if wait > 0:
            await self._sleep(wait)
