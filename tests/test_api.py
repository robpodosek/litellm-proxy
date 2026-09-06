from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError


class FakeTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[PhysicalRoute, dict[str, Any]]] = []

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((route, payload))
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


def phase1_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "routes": {
                "hidden-route": {
                    "provider": "fake-provider",
                    "model": "fake-provider/physical-model",
                    "enabled": True,
                    "free": True,
                }
            },
            "logical_models": {"free-frontier": {"routes": ["hidden-route"]}},
        }
    )


def test_models_exposes_only_logical_model() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(phase1_config(), transport))

    response = client.get("/v1/models")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == ["free-frontier"]
    assert "hidden-route" not in response.text
    assert "physical-model" not in response.text


def test_chat_completion_resolves_logical_model_to_physical_route() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(phase1_config(), transport))

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
    route, payload = transport.calls[0]
    assert route.id == "hidden-route"
    assert route.model == "fake-provider/physical-model"
    assert payload["messages"] == [{"role": "user", "content": "ping"}]
    assert payload["temperature"] == 0.2
    assert payload["stream"] is False
    assert "model" not in payload


def test_unknown_physical_or_logical_model_is_not_accepted() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(phase1_config(), transport))

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


def test_phase1_explicitly_rejects_streaming() -> None:
    transport = FakeTransport()
    client = TestClient(create_app(phase1_config(), transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_feature"
    assert transport.calls == []


def test_single_upstream_failure_returns_clean_502_without_fallback() -> None:
    transport = FakeTransport(fail=True)
    client = TestClient(create_app(phase1_config(), transport))

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
            self, route: PhysicalRoute, payload: dict[str, Any]
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
