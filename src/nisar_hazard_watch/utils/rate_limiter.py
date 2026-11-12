import time
from collections import OrderedDict, deque
from collections.abc import Callable
from threading import Lock

MAX_TRACKED_CLIENTS = 8192


class RateLimiter:
    """Sliding-window limit per client key, in memory (one process, like the deployment)."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window_seconds:
                hits.popleft()
            self._hits.move_to_end(key)
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._hits.popitem(last=False)
            if len(hits) >= self._max_requests:
                return False
            hits.append(now)
            return True
