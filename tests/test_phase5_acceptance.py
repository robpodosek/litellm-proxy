from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute

ROOT = Path(__file__).resolve().parents[1]


class ClientCompatibilityTransport:
    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": "chatcmpl-phase5",
            "object": "chat.completion",
            "model": route.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
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
                "id": "chatcmpl-phase5",
                "object": "chat.completion.chunk",
                "model": route.model,
                "choices": [
                    {"index": 0, "delta": {"content": "ok"}, "finish_reason": None}
                ],
            }

        return chunks()


def config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "routes": {
                "route-a": {
                    "provider": "provider-a",
                    "model": "provider-a/model-a",
                    "enabled": True,
                    "free": True,
                    "capabilities": ["streaming", "tools"],
                }
            },
            "logical_models": {"free-frontier": {"routes": ["route-a"]}},
        }
    )


def test_openai_compatible_client_may_send_placeholder_bearer_key() -> None:
    client = TestClient(create_app(config(), ClientCompatibilityTransport()))

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer free-frontier-local"},
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "free-frontier"


def test_phase5_packaging_and_integration_guides_exist() -> None:
    required = [
        ROOT / "Dockerfile",
        ROOT / "compose.yaml",
        ROOT / ".dockerignore",
        ROOT / "docs" / "integrations" / "HERMES.md",
        ROOT / "docs" / "integrations" / "CLINE.md",
        ROOT / "docs" / "PROVIDERS.md",
        ROOT / "docs" / "FAILURES.md",
        ROOT / "docs" / "RELEASE-CHECKLIST.md",
        ROOT / "docs" / "PHASE5-SMOKE.md",
    ]

    assert all(path.is_file() for path in required)


def test_integration_guides_preserve_logical_model_abstraction() -> None:
    hermes = (ROOT / "docs" / "integrations" / "HERMES.md").read_text()
    cline = (ROOT / "docs" / "integrations" / "CLINE.md").read_text()

    for guide in (hermes, cline):
        assert "http://127.0.0.1:4000/v1" in guide
        assert "free-frontier" in guide
        assert "GEMINI_API_KEY" not in guide or "Do not" in guide
        assert "GROQ_API_KEY" not in guide or "Do not" in guide


def test_compose_publishes_loopback_only_and_does_not_bake_secrets() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    assert '"127.0.0.1:4000:4000"' in compose
    assert ".env" in dockerignore
    assert "free-frontier.toml" in dockerignore
