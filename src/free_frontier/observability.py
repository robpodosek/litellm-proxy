from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class RouteMetrics:
    attempts: int = 0
    selections: int = 0
    successes: int = 0
    failures: int = 0
    fallback_failures: int = 0
    skips: dict[str, int] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    completed_latency_samples: int = 0
    last_selected_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_failure_kind: str | None = None
    last_failure_status: int | None = None
    last_skip_reason: str | None = None

    def snapshot(self) -> dict[str, object]:
        average_latency_ms: float | None = None
        if self.completed_latency_samples:
            average_latency_ms = self.total_latency_ms / self.completed_latency_samples

        return {
            "attempts": self.attempts,
            "selections": self.selections,
            "successes": self.successes,
            "failures": self.failures,
            "fallback_failures": self.fallback_failures,
            "skips": dict(sorted(self.skips.items())),
            "average_latency_ms": (
                round(average_latency_ms, 3) if average_latency_ms is not None else None
            ),
            "last_selected_at": self.last_selected_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_failure_kind": self.last_failure_kind,
            "last_failure_status": self.last_failure_status,
            "last_skip_reason": self.last_skip_reason,
        }


@dataclass(slots=True)
class RequestMetrics:
    total: int = 0
    in_flight: int = 0
    successes: int = 0
    failures: int = 0
    streaming: int = 0
    non_streaming: int = 0
    fallbacks: int = 0
    last_error_code: str | None = None

    def snapshot(self) -> dict[str, object]:
        return {
            "total": self.total,
            "in_flight": self.in_flight,
            "successes": self.successes,
            "failures": self.failures,
            "streaming": self.streaming,
            "non_streaming": self.non_streaming,
            "fallbacks": self.fallbacks,
            "last_error_code": self.last_error_code,
        }


class ObservabilityState:
    """Thread-safe, in-memory metrics consumed by read-only status interfaces.

    This state never participates in route eligibility, ordering, cooldown timing, or fallback
    decisions. Routing code emits outcomes here after decisions are made.
    """

    def __init__(
        self,
        route_ids: Iterable[str],
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._started_monotonic = monotonic_clock()
        self._started_at = _iso_timestamp(wall_clock())
        self._lock = Lock()
        self._requests = RequestMetrics()
        self._routes = {route_id: RouteMetrics() for route_id in route_ids}
        self._last_selected_route: str | None = None

    def _timestamp(self) -> str:
        return _iso_timestamp(self._wall_clock())

    def uptime_seconds(self) -> float:
        return max(0.0, self._monotonic_clock() - self._started_monotonic)

    @property
    def started_at(self) -> str:
        return self._started_at

    def record_request_started(self, *, streaming: bool) -> None:
        with self._lock:
            self._requests.total += 1
            self._requests.in_flight += 1
            if streaming:
                self._requests.streaming += 1
            else:
                self._requests.non_streaming += 1

    def record_request_succeeded(self) -> None:
        with self._lock:
            self._requests.in_flight = max(0, self._requests.in_flight - 1)
            self._requests.successes += 1

    def record_request_failed(self, error_code: str) -> None:
        with self._lock:
            self._requests.in_flight = max(0, self._requests.in_flight - 1)
            self._requests.failures += 1
            self._requests.last_error_code = error_code

    def record_route_skip(self, route_id: str, reason: str) -> None:
        with self._lock:
            metrics = self._routes[route_id]
            metrics.skips[reason] = metrics.skips.get(reason, 0) + 1
            metrics.last_skip_reason = reason

    def record_route_attempt(self, route_id: str) -> None:
        with self._lock:
            self._routes[route_id].attempts += 1

    def record_route_selected(self, route_id: str) -> None:
        timestamp = self._timestamp()
        with self._lock:
            metrics = self._routes[route_id]
            metrics.selections += 1
            metrics.last_selected_at = timestamp
            self._last_selected_route = route_id

    def record_route_success(self, route_id: str, *, latency_ms: float) -> None:
        timestamp = self._timestamp()
        with self._lock:
            metrics = self._routes[route_id]
            metrics.successes += 1
            metrics.completed_latency_samples += 1
            metrics.total_latency_ms += max(0.0, latency_ms)
            metrics.last_success_at = timestamp

    def record_route_failure(
        self,
        route_id: str,
        *,
        kind: str,
        status_code: int | None,
        latency_ms: float,
        fallback: bool,
    ) -> None:
        timestamp = self._timestamp()
        with self._lock:
            metrics = self._routes[route_id]
            metrics.failures += 1
            metrics.completed_latency_samples += 1
            metrics.total_latency_ms += max(0.0, latency_ms)
            metrics.last_failure_at = timestamp
            metrics.last_failure_kind = kind
            metrics.last_failure_status = status_code
            if fallback:
                metrics.fallback_failures += 1
                self._requests.fallbacks += 1

    def request_snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._requests.snapshot()

    def route_snapshot(self, route_id: str) -> dict[str, object]:
        with self._lock:
            return self._routes[route_id].snapshot()

    def status_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "started_at": self._started_at,
                "uptime_seconds": round(self.uptime_seconds(), 3),
                "last_selected_route": self._last_selected_route,
                "requests": self._requests.snapshot(),
            }
