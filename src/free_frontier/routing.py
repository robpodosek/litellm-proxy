from __future__ import annotations

from typing import Any

from free_frontier.models import AppConfig, PhysicalRoute
from free_frontier.providers.base import CompletionTransport


class UnknownLogicalModel(LookupError):
    pass


class Phase1Router:
    """Resolve one logical model to one physical route.

    This class intentionally contains no fallback/cooldown machinery. Phase 2 will evolve
    this boundary while keeping the external `free-frontier` model contract stable.
    """

    def __init__(self, config: AppConfig, transport: CompletionTransport) -> None:
        self._config = config
        self._transport = transport

    def logical_models(self) -> list[str]:
        return sorted(self._config.logical_models)

    def resolve(self, logical_model: str) -> PhysicalRoute:
        logical = self._config.logical_models.get(logical_model)
        if logical is None:
            raise UnknownLogicalModel(logical_model)

        route_id = logical.routes[0]
        route = self._config.routes[route_id]
        return PhysicalRoute(
            id=route_id,
            provider=route.provider,
            model=route.model,
            api_key_env=route.api_key_env,
            api_base=route.api_base,
            litellm_params=dict(route.litellm_params),
        )

    async def complete(self, logical_model: str, payload: dict[str, Any]) -> dict[str, Any]:
        route = self.resolve(logical_model)
        response = await self._transport.complete(route, payload)

        # The physical upstream identity is intentionally hidden from normal clients.
        # Observability can expose it later through a separate read-only interface.
        response["model"] = logical_model
        return response
