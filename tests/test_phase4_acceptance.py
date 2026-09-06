from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError


class Phase4Transport:
    def __init__(self) -> None:
        self.complete_calls: list[str] = []
        self.stream_calls: list[str] = []
        self.fail_once: set[str] = set()

    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.complete_calls.append(route.id)
        if route.id in self.fail_once:
            self.fail_once.remove(route.id)
            raise TransportError(
                "temporary test failure",
                kind=FailureKind.TEMPORARY,
                status_code=503,
            )
        return {
            "id": f"chatcmpl-{route.id}",
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

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        self.stream_calls.append(route.id)

        async def chunks() -> AsyncIterator[dict[str, Any]]:
            yield {
                "id": f"chatcmpl-{route.id}",
                "object": "chat.completion.chunk",
                "model": route.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "hello"},
                        "finish_reason": None,
                    }
                ],
            }
            yield {
                "id": f"chatcmpl-{route.id}",
                "object": "chat.completion.chunk",
                "model": route.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }

        return chunks()


def config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "routing": {"default_cooldown_seconds": 60},
            "routes": {
                "route-a": {
                    "provider": "provider-a",
                    "model": "provider-a/model-a",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools"],
                    "api_key_env": "PROVIDER_A_API_KEY",
                },
                "route-b": {
                    "provider": "provider-b",
                    "model": "provider-b/model-b",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools"],
                    "api_key_env": "PROVIDER_B_API_KEY",
                },
            },
            "logical_models": {
                "free-frontier": {"routes": ["route-a", "route-b"]}
            },
        }
    )


def completion_payload() -> dict[str, Any]:
    return {
        "model": "free-frontier",
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    }


def route_by_id(client: TestClient, route_id: str) -> dict[str, Any]:
    routes = client.get("/routes").json()["data"]
    return next(route for route in routes if route["id"] == route_id)


def test_health_and_routes_expose_safe_initial_state() -> None:
    client = TestClient(create_app(config(), Phase4Transport()))

    health = client.get("/health")
    routes = client.get("/routes")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["ready"] is True

    body = routes.json()
    assert body["logical_model"] == "free-frontier"
    assert [item["id"] for item in body["data"]] == ["route-a", "route-b"]
    assert body["data"][0]["priority"] == 1
    assert body["data"][0]["eligible_now"] is True
    assert body["data"][0]["cooldown"]["active"] is False
    assert body["data"][0]["metrics"]["attempts"] == 0

    serialized = routes.text
    assert "PROVIDER_A_API_KEY" not in serialized
    assert "PROVIDER_B_API_KEY" not in serialized


def test_success_updates_status_and_route_metrics() -> None:
    transport = Phase4Transport()
    client = TestClient(create_app(config(), transport))

    response = client.post("/v1/chat/completions", json=completion_payload())
    status = client.get("/status").json()
    route = route_by_id(client, "route-a")

    assert response.status_code == 200
    assert status["last_selected_route"] == "route-a"
    assert status["requests"] == {
        "total": 1,
        "in_flight": 0,
        "successes": 1,
        "failures": 0,
        "streaming": 0,
        "non_streaming": 1,
        "fallbacks": 0,
        "last_error_code": None,
    }
    assert route["metrics"]["attempts"] == 1
    assert route["metrics"]["selections"] == 1
    assert route["metrics"]["successes"] == 1
    assert route["metrics"]["failures"] == 0
    assert route["metrics"]["average_latency_ms"] is not None


def test_fallback_and_cooldown_are_visible_read_only() -> None:
    transport = Phase4Transport()
    transport.fail_once.add("route-a")
    client = TestClient(create_app(config(), transport))

    first = client.post("/v1/chat/completions", json=completion_payload())
    route_a = route_by_id(client, "route-a")
    status_after_first = client.get("/status").json()

    assert first.status_code == 200
    assert transport.complete_calls == ["route-a", "route-b"]
    assert route_a["cooldown"]["active"] is True
    assert route_a["cooldown"]["remaining_seconds"] > 0
    assert route_a["eligible_now"] is False
    assert route_a["metrics"]["failures"] == 1
    assert route_a["metrics"]["fallback_failures"] == 1
    assert route_a["metrics"]["last_failure_kind"] == "temporary"
    assert route_a["metrics"]["last_failure_status"] == 503
    assert status_after_first["requests"]["fallbacks"] == 1
    assert status_after_first["last_selected_route"] == "route-b"

    # Reading observability endpoints must not change routing metrics or request counts.
    client.get("/health")
    client.get("/status")
    client.get("/routes")
    assert client.get("/status").json()["requests"] == status_after_first["requests"]

    second = client.post("/v1/chat/completions", json=completion_payload())
    route_a_after_second = route_by_id(client, "route-a")

    assert second.status_code == 200
    assert transport.complete_calls == ["route-a", "route-b", "route-b"]
    assert route_a_after_second["metrics"]["attempts"] == 1
    assert route_a_after_second["metrics"]["skips"]["cooldown"] >= 1
    assert route_a_after_second["metrics"]["last_skip_reason"] == "cooldown"


def test_streaming_request_is_counted_after_stream_completes() -> None:
    transport = Phase4Transport()
    client = TestClient(create_app(config(), transport))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "stream"}],
            "stream": True,
        },
    ) as response:
        body = "".join(response.iter_text())

    status = client.get("/status").json()
    route = route_by_id(client, "route-a")

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert status["requests"]["total"] == 1
    assert status["requests"]["streaming"] == 1
    assert status["requests"]["successes"] == 1
    assert status["requests"]["in_flight"] == 0
    assert route["metrics"]["selections"] == 1
    assert route["metrics"]["successes"] == 1


def test_failed_request_is_visible_without_exposing_transport_message() -> None:
    class NonRetryableTransport(Phase4Transport):
        async def complete(
            self,
            route: PhysicalRoute,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            raise TransportError(
                "secret provider detail that must not escape",
                kind=FailureKind.NON_RETRYABLE,
                status_code=401,
            )

    client = TestClient(create_app(config(), NonRetryableTransport()))

    response = client.post("/v1/chat/completions", json=completion_payload())
    status = client.get("/status").json()
    route = route_by_id(client, "route-a")

    assert response.status_code == 502
    assert "secret provider detail" not in response.text
    assert "secret provider detail" not in client.get("/routes").text
    assert status["requests"]["failures"] == 1
    assert status["requests"]["last_error_code"] == "upstream_error"
    assert route["metrics"]["last_failure_kind"] == "non_retryable"
    assert route["metrics"]["last_failure_status"] == 401
