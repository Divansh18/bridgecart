"""Bounded in-process login limiter; single-replica scope is documented."""

import asyncio
import time


class LoginLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: int = 300) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def allow_attempt(self, key: str) -> bool:
        async with self._lock:
            self._prune(key)
            if len(self._attempts.get(key, [])) >= self.max_failures:
                return False
            self._attempts.setdefault(key, []).append(time.monotonic())
            if len(self._attempts) > 10_000:
                self._attempts.pop(next(iter(self._attempts)))
            return True

    async def succeeded(self, key: str) -> None:
        async with self._lock:
            self._attempts.pop(key, None)

    def _prune(self, key: str) -> None:
        cutoff = time.monotonic() - self.window_seconds
        recent = [timepoint for timepoint in self._attempts.get(key, []) if timepoint > cutoff]
        if recent:
            self._attempts[key] = recent
        else:
            self._attempts.pop(key, None)
