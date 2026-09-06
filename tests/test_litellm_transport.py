import asyncio
import sys
from types import SimpleNamespace
from typing import Any

from free_frontier.models import PhysicalRoute
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
