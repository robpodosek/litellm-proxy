from __future__ import annotations

import os
from typing import Any

from free_frontier.models import PhysicalRoute
from free_frontier.providers.base import TransportError


class LiteLLMTransport:
    """Provider-normalization transport backed by LiteLLM's Python SDK."""

    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # Import at call time so deterministic unit tests can use fake transports without
        # importing or initializing LiteLLM/provider integrations.
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - packaging/runtime guard
            raise TransportError("LiteLLM is not installed") from exc

        kwargs: dict[str, Any] = {
            **payload,
            **route.litellm_params,
            "model": route.model,
            "stream": False,
        }

        if route.api_key_env:
            api_key = os.getenv(route.api_key_env)
            if not api_key:
                # Startup validation should catch this. Keep a second safe check here for
                # callers that construct application objects directly.
                raise TransportError(
                    f"Credential environment variable {route.api_key_env} is not set"
                )
            kwargs["api_key"] = api_key

        if route.api_base:
            kwargs["api_base"] = route.api_base

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            # Phase 2 will classify errors for fallback/cooldown policy. Phase 1 has one
            # route, so normalize the transport failure without leaking request secrets.
            raise TransportError(
                f"Upstream route '{route.id}' failed via provider '{route.provider}'"
            ) from exc

        if isinstance(response, dict):
            return dict(response)
        if hasattr(response, "model_dump"):
            return response.model_dump()

        try:
            return dict(response)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive adapter guard
            raise TransportError("LiteLLM returned an unsupported response type") from exc
