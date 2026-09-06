from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import pytest

from free_frontier.cooldowns import CooldownTracker
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError
from free_frontier.routing import AllRoutesUnavailable, Router


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedTransport:
    def __init__(self, outcomes: dict[str, list[dict[str, Any] | Exception]]) -> None:
        self.outcomes = {route_id: list(values) for route_id, values in outcomes.items()}
        self.calls: list[str] = []
        self.call_counts: dict[str, int] = defaultdict(int)

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(route.id)
        self.call_counts[route.id] += 1
        queue = self.outcomes.setdefault(route.id, [])
        if not queue:
            return response(route, f"{route.id}-ok")

        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(route: PhysicalRoute, content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{route.id}",
        "object": "chat.completion",
        "model": route.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def fallback_error(
    kind: FailureKind = FailureKind.RATE_LIMIT,
    *,
    retry_after_seconds: float | None = None,
) -> TransportError:
    return TransportError(
        "fake fallback-worthy failure",
        kind=kind,
        status_code=429 if kind == FailureKind.RATE_LIMIT else 503,
        retry_after_seconds=retry_after_seconds,
    )


def config(
    *,
    route_a_free: bool = True,
    route_a_enabled: bool = True,
    cooldown_seconds: float = 60,
) -> AppConfig:
    return AppConfig.model_validate(
        {
            "routing": {"default_cooldown_seconds": cooldown_seconds},
            "routes": {
                "route-a": {
                    "provider": "provider-a",
                    "model": "provider-a/model-a",
                    "enabled": route_a_enabled,
                    "free": route_a_free,
                },
                "route-b": {
                    "provider": "provider-b",
                    "model": "provider-b/model-b",
                    "enabled": True,
                    "free": True,
                },
            },
            "logical_models": {"free-frontier": {"routes": ["route-a", "route-b"]}},
        }
    )


def make_router(
    app_config: AppConfig,
    transport: ScriptedTransport,
    clock: FakeClock,
) -> Router:
    return Router(app_config, transport, cooldowns=CooldownTracker(clock=clock))


def complete(router: Router) -> dict[str, Any]:
    return asyncio.run(
        router.complete(
            "free-frontier",
            {"messages": [{"role": "user", "content": "ping"}], "stream": False},
        )
    )


def test_preferred_route_succeeds_without_touching_fallback() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({})
    router = make_router(config(), transport, clock)

    result = complete(router)

    assert transport.calls == ["route-a"]
    assert result["model"] == "free-frontier"
    assert result["choices"][0]["message"]["content"] == "route-a-ok"


def test_rate_limit_falls_back_to_next_free_route() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({"route-a": [fallback_error()]})
    router = make_router(config(), transport, clock)

    result = complete(router)

    assert transport.calls == ["route-a", "route-b"]
    assert result["model"] == "free-frontier"
    assert result["choices"][0]["message"]["content"] == "route-b-ok"


def test_next_request_skips_preferred_route_during_cooldown() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({"route-a": [fallback_error()]})
    router = make_router(config(cooldown_seconds=60), transport, clock)

    complete(router)
    transport.calls.clear()
    result = complete(router)

    assert transport.calls == ["route-b"]
    assert result["choices"][0]["message"]["content"] == "route-b-ok"


def test_expired_cooldown_restores_preferred_route() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({"route-a": [fallback_error()]})
    router = make_router(config(cooldown_seconds=60), transport, clock)

    complete(router)
    clock.advance(60)
    transport.calls.clear()
    result = complete(router)

    assert transport.calls == ["route-a"]
    assert result["choices"][0]["message"]["content"] == "route-a-ok"


def test_provider_retry_after_can_extend_configured_cooldown() -> None:
    clock = FakeClock()
    transport = ScriptedTransport(
        {"route-a": [fallback_error(retry_after_seconds=120)]}
    )
    router = make_router(config(cooldown_seconds=30), transport, clock)

    complete(router)
    clock.advance(60)
    transport.calls.clear()
    complete(router)

    assert transport.calls == ["route-b"]

    clock.advance(60)
    transport.calls.clear()
    complete(router)
    assert transport.calls == ["route-a"]


def test_all_free_routes_unavailable_fails_cleanly() -> None:
    clock = FakeClock()
    transport = ScriptedTransport(
        {
            "route-a": [fallback_error()],
            "route-b": [fallback_error(FailureKind.TEMPORARY)],
        }
    )
    router = make_router(config(), transport, clock)

    with pytest.raises(AllRoutesUnavailable):
        complete(router)

    assert transport.calls == ["route-a", "route-b"]


def test_paid_route_is_never_selected_even_when_first_in_order() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({})
    router = make_router(config(route_a_free=False), transport, clock)

    result = complete(router)

    assert transport.calls == ["route-b"]
    assert result["choices"][0]["message"]["content"] == "route-b-ok"


def test_disabled_route_is_never_selected() -> None:
    clock = FakeClock()
    transport = ScriptedTransport({})
    router = make_router(config(route_a_enabled=False), transport, clock)

    complete(router)

    assert transport.calls == ["route-b"]


def test_non_retryable_failure_does_not_silently_fallback() -> None:
    clock = FakeClock()
    error = TransportError("bad request", kind=FailureKind.NON_RETRYABLE, status_code=400)
    transport = ScriptedTransport({"route-a": [error]})
    router = make_router(config(), transport, clock)

    with pytest.raises(TransportError) as exc_info:
        complete(router)

    assert exc_info.value is error
    assert transport.calls == ["route-a"]
