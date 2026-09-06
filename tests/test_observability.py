from free_frontier.observability import ObservabilityState


class Clock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_observability_snapshots_are_deterministic_and_credential_free() -> None:
    monotonic = Clock(100.0)
    wall = Clock(1_700_000_000.0)
    state = ObservabilityState(
        ["route-a"],
        monotonic_clock=monotonic,
        wall_clock=wall,
    )

    state.record_request_started(streaming=False)
    state.record_route_attempt("route-a")
    state.record_route_selected("route-a")
    state.record_route_success("route-a", latency_ms=25.0)
    state.record_request_succeeded()

    monotonic.value = 102.5
    status = state.status_snapshot()
    route = state.route_snapshot("route-a")

    assert status["uptime_seconds"] == 2.5
    assert status["last_selected_route"] == "route-a"
    assert status["requests"]["successes"] == 1
    assert route["average_latency_ms"] == 25.0
    assert route["last_selected_at"] is not None
    assert route["last_success_at"] is not None


def test_route_failure_and_skip_metrics_are_recorded() -> None:
    state = ObservabilityState(["route-a"])

    state.record_route_attempt("route-a")
    state.record_route_failure(
        "route-a",
        kind="rate_limit",
        status_code=429,
        latency_ms=10.0,
        fallback=True,
    )
    state.record_route_skip("route-a", "cooldown")

    route = state.route_snapshot("route-a")
    requests = state.request_snapshot()

    assert route["attempts"] == 1
    assert route["failures"] == 1
    assert route["fallback_failures"] == 1
    assert route["last_failure_kind"] == "rate_limit"
    assert route["last_failure_status"] == 429
    assert route["skips"] == {"cooldown": 1}
    assert requests["fallbacks"] == 1
