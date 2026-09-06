from __future__ import annotations

import time
from collections.abc import Callable


class CooldownTracker:
    """In-memory route cooldown state independent of any presentation layer."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._until: dict[str, float] = {}

    def start(self, route_id: str, seconds: float) -> None:
        if seconds <= 0:
            self._until.pop(route_id, None)
            return
        self._until[route_id] = self._clock() + seconds

    def remaining(self, route_id: str) -> float:
        until = self._until.get(route_id)
        if until is None:
            return 0.0

        remaining = until - self._clock()
        if remaining <= 0:
            self._until.pop(route_id, None)
            return 0.0
        return remaining

    def is_cooling_down(self, route_id: str) -> bool:
        return self.remaining(route_id) > 0
