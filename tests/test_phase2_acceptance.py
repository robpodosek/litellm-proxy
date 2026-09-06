from __future__ import annotations

import asyncio
from typing import Any

from free_frontier.cooldowns import CooldownTracker
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError
from free_frontier.routing import Router


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class AcceptanceTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_preferred_once = True

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(route.id)
        if route.id == "preferred" and self.fail_preferred_once:
            self.fail_preferred_once = False
            raise TransportError(
                "rate limited",
                kind=FailureKind.RATE_LIMIT,
                status_code=429,
            )
        return {
            "id": "chatcmpl-acceptance",
            "object": "chat.completion",
            "model": route.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": route.id},
                    "finish_reason": "stop",
                }
            ],
        }


def test_phase2_acceptance_gate_fallback_cooldown_and_reeligibility() -> None:
    config = AppConfig.model_validate(
        {
            "routing": {"default_cooldown_seconds": 30},
            "routes": {
                "preferred": {
                    "provider": "a",
                    "model": "a/model",
                    "enabled": True,
                    "free": True,
                },
                "fallback": {
                    "provider": "b",
                    "model": "b/model",
                    "enabled": True,
                    "free": True,
                },
                "paid-never": {
                    "provider": "c",
                    "model": "c/paid",
                    "enabled": True,
                    "free": False,
                },
            },
            "logical_models": {
                "free-frontier": {"routes": ["preferred", "paid-never", "fallback"]}
            },
        }
    )
    clock = FakeClock()
    transport = AcceptanceTransport()
    router = Router(config, transport, cooldowns=CooldownTracker(clock=clock))
    payload = {"messages": [{"role": "user", "content": "ping"}], "stream": False}

    first = asyncio.run(router.complete("free-frontier", payload))
    assert transport.calls == ["preferred", "fallback"]
    assert first["model"] == "free-frontier"

    transport.calls.clear()
    second = asyncio.run(router.complete("free-frontier", payload))
    assert transport.calls == ["fallback"]
    assert second["model"] == "free-frontier"

    clock.now = 30
    transport.calls.clear()
    third = asyncio.run(router.complete("free-frontier", payload))
    assert transport.calls == ["preferred"]
    assert third["model"] == "free-frontier"
