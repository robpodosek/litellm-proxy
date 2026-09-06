from __future__ import annotations

import logging
from typing import Any

from free_frontier.cooldowns import CooldownTracker
from free_frontier.models import AppConfig, PhysicalRoute, RouteDefinition
from free_frontier.providers.base import CompletionTransport, TransportError

logger = logging.getLogger("uvicorn.error.free_frontier.routing")


class UnknownLogicalModel(LookupError):
    pass


class AllRoutesUnavailable(RuntimeError):
    pass


class Router:
    """Resolve one logical model across ordered, free-only Phase 2 routes."""

    def __init__(
        self,
        config: AppConfig,
        transport: CompletionTransport,
        *,
        cooldowns: CooldownTracker | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._cooldowns = cooldowns or CooldownTracker()

    def logical_models(self) -> list[str]:
        return sorted(self._config.logical_models)

    def _physical_route(
        self,
        route_id: str,
        route: RouteDefinition,
    ) -> PhysicalRoute:
        return PhysicalRoute(
            id=route_id,
            provider=route.provider,
            model=route.model,
            api_key_env=route.api_key_env,
            api_base=route.api_base,
            litellm_params=dict(route.litellm_params),
        )

    def _cooldown_seconds(
        self,
        route: RouteDefinition,
        error: TransportError,
    ) -> float:
        configured = (
            route.cooldown_seconds
            if route.cooldown_seconds is not None
            else self._config.routing.default_cooldown_seconds
        )

        if error.retry_after_seconds is None:
            return configured

        return max(configured, error.retry_after_seconds)

    async def complete(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        logical = self._config.logical_models.get(logical_model)
        if logical is None:
            raise UnknownLogicalModel(logical_model)

        attempted = False

        for route_id in logical.routes:
            route = self._config.routes[route_id]

            # v0.1 cost policy is enforced here even if a paid route appears in config.
            if not route.enabled or not route.free:
                logger.info(
                    "route=%s event=skipped reason=ineligible",
                    route_id,
                )
                continue

            remaining = self._cooldowns.remaining(route_id)
            if remaining > 0:
                logger.info(
                    "route=%s event=skipped reason=cooldown remaining=%.1f",
                    route_id,
                    remaining,
                )
                continue

            attempted = True
            physical = self._physical_route(route_id, route)

            logger.info(
                "route=%s event=attempt",
                route_id,
            )

            try:
                response = await self._transport.complete(
                    physical,
                    payload,
                )
            except TransportError as exc:
                if not exc.fallback_worthy:
                    logger.error(
                        "route=%s event=failed kind=%s status=%s fallback=false",
                        route_id,
                        exc.kind,
                        exc.status_code,
                    )
                    raise

                cooldown_seconds = self._cooldown_seconds(route, exc)
                self._cooldowns.start(route_id, cooldown_seconds)

                logger.warning(
                    (
                        "route=%s event=failed kind=%s status=%s "
                        "fallback=true cooldown=%.1f"
                    ),
                    route_id,
                    exc.kind,
                    exc.status_code,
                    cooldown_seconds,
                )
                continue

            logger.info(
                "route=%s event=success",
                route_id,
            )

            # The physical upstream identity is intentionally hidden from normal clients.
            response["model"] = logical_model
            return response

        if attempted:
            raise AllRoutesUnavailable("all eligible routes failed")

        raise AllRoutesUnavailable(
            "no eligible routes are currently available",
        )