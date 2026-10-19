import time

from api.auth.domain.exceptions import RateLimitExceededError


class RateLimiter:
    """In-process fixed-window rate limiter keyed by an arbitrary string."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = {}

    async def check(self, key: str) -> None:
        now = time.monotonic()
        timestamps = self._timestamps.setdefault(key, [])
        cutoff = now - self._window_seconds
        pruned = [timestamp for timestamp in timestamps if timestamp > cutoff]
        if len(pruned) >= self._max_requests:
            self._timestamps[key] = pruned
            raise RateLimitExceededError()
        pruned.append(now)
        self._timestamps[key] = pruned
