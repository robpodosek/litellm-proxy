import asyncio
import sys
from types import SimpleNamespace
from typing import Any

from free_frontier.models import PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError
from free_frontier.providers.litellm import LiteLLMTransport


def test_litellm_transport_calls_acompletion_with_internal_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def model_dump(self) -> dict[str, Any]:
            return {
                "id": "chatcmpl-litellm",
                "object": "chat.completion",
                "model": "gemini/gemini-3.6-flash",
                "choices": [],
            }

    async def fake_acompletion(**kwargs: Any) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-value")

    route = PhysicalRoute(
        id="gemini-flash",
        provider="gemini",
        model="gemini/gemini-3.6-flash",
        api_key_env="GEMINI_API_KEY",
        api_base=None,
        litellm_params={},
    )

    response = asyncio.run(
        LiteLLMTransport().complete(
            route,
            {
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
            },
        )
    )

    assert captured["model"] == "gemini/gemini-3.6-flash"
    assert captured["api_key"] == "secret-test-value"
    assert captured["messages"] == [{"role": "user", "content": "ping"}]
    assert captured["stream"] is False
    assert response["id"] == "chatcmpl-litellm"


def test_litellm_transport_classifies_rate_limit_for_fallback(monkeypatch) -> None:
    class RateLimitError(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "7"})

    async def fake_acompletion(**kwargs: Any) -> None:
        raise RateLimitError("limited")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))

    route = PhysicalRoute(
        id="rate-limited",
        provider="fake",
        model="fake/model",
        api_key_env=None,
        api_base=None,
        litellm_params={},
    )

    try:
        asyncio.run(LiteLLMTransport().complete(route, {"messages": [], "stream": False}))
    except TransportError as exc:
        assert exc.kind == FailureKind.RATE_LIMIT
        assert exc.fallback_worthy is True
        assert exc.status_code == 429
        assert exc.retry_after_seconds == 7
    else:  # pragma: no cover - test guard
        raise AssertionError("expected TransportError")


def test_litellm_transport_classifies_not_found_as_route_unavailable(monkeypatch) -> None:
    class NotFoundError(Exception):
        status_code = 404

    async def fake_acompletion(**kwargs: Any) -> None:
        raise NotFoundError("model gone")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))

    route = PhysicalRoute(
        id="stale-model",
        provider="fake",
        model="fake/stale",
        api_key_env=None,
        api_base=None,
        litellm_params={},
    )

    try:
        asyncio.run(LiteLLMTransport().complete(route, {"messages": [], "stream": False}))
    except TransportError as exc:
        assert exc.kind == FailureKind.ROUTE_UNAVAILABLE
        assert exc.fallback_worthy is True
        assert exc.status_code == 404
    else:  # pragma: no cover - test guard
        raise AssertionError("expected TransportError")
