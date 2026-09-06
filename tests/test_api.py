from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError


class FakeTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, PhysicalRoute, dict[str, Any]]] = []

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("complete", route, payload))
        if self.fail:
            raise TransportError("fake upstream failed")
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": route.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(("stream", route, payload))

        async def chunks() -> AsyncIterator[dict[str, Any]]:
            yield {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": route.model,
                "choices": [{"index": 0, "delta": {"content": "pong"}, "finish_reason": None}],
            }
            yield {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": route.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }

        return chunks()


def app_config(*, capabilities: list[str] | None = None) -> AppConfig:
    return AppConfig.model_validate(
        {
            "routes": {
                "hidden-route": {
                    "provider": "fake-provider",
                    "model": "fake-provider/physical-model",
                    "enabled": True,
                    "free": True,
                    "capabilities": capabilities or [],
                }
            },
            "logical_models": {"free-frontier": {"routes": ["hidden-route"]}},
        }
    )


def test_models_exposes_only_logical_model() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(app_config(), transport))

    response = client.get("/v1/models")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == ["free-frontier"]
    assert "hidden-route" not in response.text
    assert "physical-model" not in response.text


def test_chat_completion_resolves_logical_model_to_physical_route() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(app_config(), transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0.2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "free-frontier"
    assert body["choices"][0]["message"]["content"] == "pong"

    assert len(transport.calls) == 1
    mode, route, payload = transport.calls[0]
    assert mode == "complete"
    assert route.id == "hidden-route"
    assert route.model == "fake-provider/physical-model"
    assert payload["messages"] == [{"role": "user", "content": "ping"}]
    assert payload["temperature"] == 0.2
    assert payload["stream"] is False
    assert "model" not in payload


def test_unknown_physical_or_logical_model_is_not_accepted() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(app_config(), transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-provider/physical-model",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert transport.calls == []


def test_streaming_returns_openai_compatible_sse_and_logical_model() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(app_config(capabilities=["streaming"]), transport))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": True,
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"model":"free-frontier"' in body
    assert "fake-provider/physical-model" not in body
    assert "data: [DONE]" in body
    assert transport.calls[0][0] == "stream"
    assert transport.calls[0][2]["stream"] is True


def test_streaming_request_without_compatible_route_returns_clean_400() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(app_config(), transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_capabilities"
    assert transport.calls == []


def test_tool_request_is_forwarded_and_tool_calls_remain_compatible() -> None:
    class ToolTransport(FakeTransport):
        async def complete(
            self,
            route: PhysicalRoute,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append(("complete", route, payload))
            return {
                "id": "chatcmpl-tools",
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
                                    "id": "call_123",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": '{"city":"Seattle"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }

    transport = ToolTransport()
    client = TestClient(create_app(app_config(capabilities=["tools"]), transport))
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "weather in Seattle"}],
            "tools": tools,
            "tool_choice": "required",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "free-frontier"
    assert body["choices"][0]["finish_reason"] == "tool_calls"
    assert body["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == (
        "lookup_weather"
    )
    assert transport.calls[0][2]["tools"] == tools
    assert transport.calls[0][2]["tool_choice"] == "required"


def test_single_upstream_failure_returns_clean_502_without_fallback() -> None:
    transport = FakeTransport(fail=True)
    client = TestClient(create_app(app_config(), transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"
    assert len(transport.calls) == 1


def test_all_fallback_worthy_routes_unavailable_returns_clean_503() -> None:
    class TemporaryFailTransport:
        async def complete(
            self,
            route: PhysicalRoute,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            raise TransportError(
                "temporary",
                kind=FailureKind.TEMPORARY,
                status_code=503,
            )

    raw = {
        "routes": {
            "a": {"provider": "a", "model": "a/model", "enabled": True, "free": True},
            "b": {"provider": "b", "model": "b/model", "enabled": True, "free": True},
        },
        "logical_models": {"free-frontier": {"routes": ["a", "b"]}},
    }
    client = TestClient(create_app(AppConfig.model_validate(raw), TemporaryFailTransport()))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "all_routes_unavailable"
