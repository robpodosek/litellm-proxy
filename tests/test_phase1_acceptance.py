from typing import Any

from fastapi.testclient import TestClient

from free_frontier.app import create_app
from free_frontier.models import AppConfig, PhysicalRoute


class AcceptanceTransport:
    def __init__(self) -> None:
        self.route_seen: PhysicalRoute | None = None

    async def complete(self, route: PhysicalRoute, payload: dict[str, Any]) -> dict[str, Any]:
        self.route_seen = route
        return {
            "id": "chatcmpl-acceptance",
            "object": "chat.completion",
            "created": 1,
            "model": route.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "phase-one-ok"},
                    "finish_reason": "stop",
                }
            ],
        }


def test_phase1_acceptance_gate_client_never_names_physical_route() -> None:
    config = AppConfig.model_validate(
        {
            "routes": {
                "internal-gemini": {
                    "provider": "gemini",
                    "model": "gemini/gemini-3.6-flash",
                    "enabled": True,
                    "free": True,
                }
            },
            "logical_models": {"free-frontier": {"routes": ["internal-gemini"]}},
        }
    )
    transport = AcceptanceTransport()
    client = TestClient(create_app(config, transport))

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "free-frontier",
            "messages": [{"role": "user", "content": "prove the abstraction"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "free-frontier"
    assert transport.route_seen is not None
    assert transport.route_seen.model == "gemini/gemini-3.6-flash"
    assert "gemini/gemini-3.6-flash" not in response.text
