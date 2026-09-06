from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError
from free_frontier.routing import NoCompatibleRoutes, Router


def chunk(route: PhysicalRoute, content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{route.id}",
        "object": "chat.completion.chunk",
        "model": route.model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }


class Phase3Transport:
    def __init__(self) -> None:
        self.complete_calls: list[str] = []
        self.stream_calls: list[str] = []
        self.stream_mode: dict[str, str] = {}

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.complete_calls.append(route.id)
        return {
            "id": f"chatcmpl-{route.id}",
            "object": "chat.completion",
            "model": route.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        self.stream_calls.append(route.id)
        mode = self.stream_mode.get(route.id, "success")

        async def chunks() -> AsyncIterator[dict[str, Any]]:
            if mode == "fail_before_first":
                raise TransportError(
                    "temporary pre-stream failure",
                    kind=FailureKind.TEMPORARY,
                    status_code=503,
                )
            yield chunk(route, f"{route.id}-first")
            if mode == "fail_after_first":
                raise TransportError(
                    "temporary post-commit failure",
                    kind=FailureKind.TEMPORARY,
                    status_code=503,
                )
            yield chunk(route, f"{route.id}-second")

        return chunks()


def config(
    *,
    route_a: list[str],
    route_b: list[str],
) -> AppConfig:
    return AppConfig.model_validate(
        {
            "routes": {
                "route-a": {
                    "provider": "a",
                    "model": "a/model",
                    "enabled": True,
                    "free": True,
                    "capabilities": route_a,
                },
                "route-b": {
                    "provider": "b",
                    "model": "b/model",
                    "enabled": True,
                    "free": True,
                    "capabilities": route_b,
                },
            },
            "logical_models": {"free-frontier": {"routes": ["route-a", "route-b"]}},
        }
    )


def test_tools_request_skips_route_without_tool_support() -> None:
    transport = Phase3Transport()
    router = Router(config(route_a=["streaming"], route_b=["tools"]), transport)

    result = asyncio.run(
        router.complete(
            "free-frontier",
            {
                "messages": [{"role": "user", "content": "use the tool"}],
                "stream": False,
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
            },
        )
    )

    assert transport.complete_calls == ["route-b"]
    assert result["model"] == "free-frontier"
    assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "lookup"


def test_streaming_request_skips_route_without_streaming_support() -> None:
    transport = Phase3Transport()
    router = Router(config(route_a=["tools"], route_b=["streaming"]), transport)

    async def collect() -> list[dict[str, Any]]:
        stream = await router.stream(
            "free-frontier",
            {"messages": [{"role": "user", "content": "stream"}], "stream": True},
        )
        return [item async for item in stream]

    chunks = asyncio.run(collect())

    assert transport.stream_calls == ["route-b"]
    assert [item["model"] for item in chunks] == ["free-frontier", "free-frontier"]


def test_pre_stream_failure_falls_back_transparently() -> None:
    transport = Phase3Transport()
    transport.stream_mode["route-a"] = "fail_before_first"
    router = Router(config(route_a=["streaming"], route_b=["streaming"]), transport)

    async def collect() -> list[dict[str, Any]]:
        stream = await router.stream(
            "free-frontier",
            {"messages": [{"role": "user", "content": "stream"}], "stream": True},
        )
        return [item async for item in stream]

    chunks = asyncio.run(collect())

    assert transport.stream_calls == ["route-a", "route-b"]
    assert chunks[0]["choices"][0]["delta"]["content"] == "route-b-first"
    assert all(item["model"] == "free-frontier" for item in chunks)


def test_partial_stream_is_never_spliced_with_fallback_route() -> None:
    transport = Phase3Transport()
    transport.stream_mode["route-a"] = "fail_after_first"
    router = Router(config(route_a=["streaming"], route_b=["streaming"]), transport)

    async def consume() -> list[str]:
        stream = await router.stream(
            "free-frontier",
            {"messages": [{"role": "user", "content": "stream"}], "stream": True},
        )
        seen: list[str] = []
        async for item in stream:
            seen.append(item["choices"][0]["delta"]["content"])
        return seen

    with pytest.raises(TransportError):
        asyncio.run(consume())

    assert transport.stream_calls == ["route-a"]


def test_structured_output_requires_compatible_route() -> None:
    transport = Phase3Transport()
    router = Router(
        config(route_a=["streaming"], route_b=["structured_output"]),
        transport,
    )

    asyncio.run(
        router.complete(
            "free-frontier",
            {
                "messages": [{"role": "user", "content": "json please"}],
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
    )

    assert transport.complete_calls == ["route-b"]


def test_request_fails_cleanly_when_no_route_supports_required_capabilities() -> None:
    transport = Phase3Transport()
    router = Router(config(route_a=["streaming"], route_b=["tools"]), transport)

    with pytest.raises(NoCompatibleRoutes) as exc_info:
        asyncio.run(
            router.complete(
                "free-frontier",
                {
                    "messages": [{"role": "user", "content": "json please"}],
                    "stream": False,
                    "response_format": {"type": "json_schema"},
                },
            )
        )

    assert "structured_output" in str(exc_info.value)
    assert transport.complete_calls == []
