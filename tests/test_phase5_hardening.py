from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(route.id)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": route.model,
            "provider_specific_fields": {"secretish": "provider-only"},
            "x_groq": {"provider": "groq"},
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                        "provider_specific_fields": {"trace": "provider-only"},
                    },
                    "finish_reason": "stop",
                }
            ],
        }

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        async def chunks() -> AsyncIterator[dict[str, Any]]:
            yield {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "model": route.model,
                "provider_specific_fields": {"trace": "provider-only"},
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": "ok",
                            "provider_specific_fields": {"trace": "provider-only"},
                        },
                        "finish_reason": None,
                    }
                ],
            }

        return chunks()


def base_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "routes": {
                "route-a": {
                    "provider": "a",
                    "model": "a/model",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools", "structured_output"],
                }
            },
            "logical_models": {"free-frontier": {"routes": ["route-a"]}},
        }
    )


def test_model_detail_endpoint_exposes_only_logical_model() -> None:
    client = TestClient(create_app(base_config(), RecordingTransport()))

    response = client.get("/v1/models/free-frontier")

    assert response.status_code == 200
    assert response.json()["id"] == "free-frontier"
    assert response.json()["owned_by"] == "free-frontier"
    assert "a/model" not in response.text

    missing = client.get("/v1/models/not-a-model")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "model_not_found"


def test_chat_response_includes_request_id_and_routing_logs_are_correlated(caplog) -> None:
    client = TestClient(create_app(base_config(), RecordingTransport()))
    caplog.set_level(logging.INFO, logger="uvicorn.error.free_frontier.routing")

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 12
    assert any(
        f"request={request_id} route=route-a event=attempt" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        f"request={request_id} route=route-a event=success" in record.getMessage()
        for record in caplog.records
    )


def test_known_top_level_provider_diagnostics_are_removed() -> None:
    client = TestClient(create_app(base_config(), RecordingTransport()))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "free-frontier"
    assert "x_groq" not in response.json()
    assert response.json()["provider_specific_fields"]["secretish"] == "provider-only"
    assert (
        response.json()["choices"][0]["message"]["provider_specific_fields"]["trace"]
        == "provider-only"
    )


def test_streaming_response_preserves_nested_compatibility_metadata() -> None:
    client = TestClient(create_app(base_config(), RecordingTransport()))

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
    assert '"model":"free-frontier"' in body
    assert "provider_specific_fields" in body
    assert "data: [DONE]" in body


def test_incompatible_capability_combination_skips_route_before_inference() -> None:
    config = AppConfig.model_validate(
        {
            "routes": {
                "restricted": {
                    "provider": "a",
                    "model": "a/model",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools", "structured_output"],
                    "incompatible_capability_combinations": [
                        ["structured_output", "tools"]
                    ],
                },
                "compatible": {
                    "provider": "b",
                    "model": "b/model",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools", "structured_output"],
                },
            },
            "logical_models": {
                "free-frontier": {"routes": ["restricted", "compatible"]}
            },
        }
    )
    transport = RecordingTransport()
    client = TestClient(create_app(config, transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "noop",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "response_format": {"type": "json_object"},
        },
    )

    assert response.status_code == 200
    assert transport.calls == ["compatible"]


def test_hermes_failure_sequence_returns_retry_after_then_skips_cooling_routes() -> None:
    class FailingTransport:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def complete(
            self,
            route: PhysicalRoute,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append(route.id)
            if route.id == "gemini-flash":
                raise TransportError(
                    "temporary service failure",
                    kind=FailureKind.TEMPORARY,
                    status_code=503,
                    retry_after_seconds=12,
                )
            raise TransportError(
                "rate limited",
                kind=FailureKind.RATE_LIMIT,
                status_code=429,
                retry_after_seconds=30,
            )

    config = AppConfig.model_validate(
        {
            "routing": {"default_cooldown_seconds": 5},
            "routes": {
                "gemini-flash": {
                    "provider": "gemini",
                    "model": "gemini/model",
                    "enabled": True,
                    "free": True,
                },
                "groq-gpt-oss": {
                    "provider": "groq",
                    "model": "groq/model",
                    "enabled": True,
                    "free": True,
                },
            },
            "logical_models": {
                "free-frontier": {"routes": ["gemini-flash", "groq-gpt-oss"]}
            },
        }
    )
    transport = FailingTransport()
    client = TestClient(create_app(config, transport))
    request_body = {
        "model": "free-frontier",
        "messages": [{"role": "user", "content": "ping"}],
    }

    first = client.post("/v1/chat/completions", json=request_body)

    assert first.status_code == 503
    assert first.json()["error"]["code"] == "all_routes_unavailable"
    assert first.json()["error"]["retry_after_seconds"] == 12
    assert first.headers["retry-after"] == "12"
    assert transport.calls == ["gemini-flash", "groq-gpt-oss"]

    second = client.post("/v1/chat/completions", json=request_body)

    assert second.status_code == 503
    assert second.headers["retry-after"] in {"11", "12"}
    assert transport.calls == ["gemini-flash", "groq-gpt-oss"]


def test_unrelated_backend_probe_is_not_faked() -> None:
    client = TestClient(create_app(base_config(), RecordingTransport()))

    response = client.get("/api/tags")

    assert response.status_code == 404
