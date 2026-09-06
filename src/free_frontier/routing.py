from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from free_frontier.capabilities import missing_capabilities, required_capabilities
from free_frontier.cooldowns import CooldownTracker
from free_frontier.models import AppConfig, Capability, PhysicalRoute, RouteDefinition
from free_frontier.providers.base import CompletionTransport, FailureKind, TransportError

logger = logging.getLogger("uvicorn.error.free_frontier.routing")


class UnknownLogicalModel(LookupError):
    pass


class AllRoutesUnavailable(RuntimeError):
    pass


class NoCompatibleRoutes(RuntimeError):
    def __init__(self, required: frozenset[Capability]) -> None:
        self.required = required
        names = ", ".join(sorted(capability.value for capability in required)) or "none"
        super().__init__(f"no eligible route supports required capabilities: {names}")


class Router:
    """Resolve one logical model across ordered, free-only, compatible routes."""

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
            capabilities=route.capabilities,
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

    def _logical_routes(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> tuple[list[tuple[str, RouteDefinition]], frozenset[Capability]]:
        logical = self._config.logical_models.get(logical_model)
        if logical is None:
            raise UnknownLogicalModel(logical_model)

        required = required_capabilities(payload)
        compatible: list[tuple[str, RouteDefinition]] = []
        eligible_free_seen = False

        for route_id in logical.routes:
            route = self._config.routes[route_id]
            if not route.enabled or not route.free:
                logger.info("route=%s event=skipped reason=ineligible", route_id)
                continue

            eligible_free_seen = True
            missing = missing_capabilities(route.capabilities, required)
            if missing:
                logger.info(
                    "route=%s event=skipped reason=capability missing=%s",
                    route_id,
                    ",".join(sorted(capability.value for capability in missing)),
                )
                continue

            compatible.append((route_id, route))

        if eligible_free_seen and not compatible:
            raise NoCompatibleRoutes(required)

        return compatible, required

    def _available_routes(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> list[tuple[str, RouteDefinition]]:
        compatible, _ = self._logical_routes(logical_model, payload)
        available: list[tuple[str, RouteDefinition]] = []

        for route_id, route in compatible:
            remaining = self._cooldowns.remaining(route_id)
            if remaining > 0:
                logger.info(
                    "route=%s event=skipped reason=cooldown remaining=%.1f",
                    route_id,
                    remaining,
                )
                continue
            available.append((route_id, route))

        return available

    def _record_failure(
        self,
        route_id: str,
        route: RouteDefinition,
        error: TransportError,
    ) -> bool:
        if not error.fallback_worthy:
            logger.error(
                "route=%s event=failed kind=%s status=%s fallback=false",
                route_id,
                error.kind,
                error.status_code,
            )
            return False

        cooldown_seconds = self._cooldown_seconds(route, error)
        self._cooldowns.start(route_id, cooldown_seconds)
        logger.warning(
            "route=%s event=failed kind=%s status=%s fallback=true cooldown=%.1f",
            route_id,
            error.kind,
            error.status_code,
            cooldown_seconds,
        )
        return True

    async def complete(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        attempted = False

        for route_id, route in self._available_routes(logical_model, payload):
            attempted = True
            physical = self._physical_route(route_id, route)
            logger.info("route=%s event=attempt mode=completion", route_id)

            try:
                response = await self._transport.complete(physical, payload)
            except TransportError as exc:
                if self._record_failure(route_id, route, exc):
                    continue
                raise

            logger.info("route=%s event=success mode=completion", route_id)
            response["model"] = logical_model
            return response

        if attempted:
            raise AllRoutesUnavailable("all eligible routes failed")
        raise AllRoutesUnavailable("no eligible routes are currently available")

    async def stream(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Start a stream, allowing fallback only before the first upstream chunk."""

        attempted = False

        for route_id, route in self._available_routes(logical_model, payload):
            attempted = True
            physical = self._physical_route(route_id, route)
            logger.info("route=%s event=attempt mode=stream", route_id)

            try:
                upstream = await self._transport.stream(physical, payload)
                first_chunk = await anext(upstream)
            except StopAsyncIteration:
                error = TransportError(
                    "upstream stream ended before producing a chunk",
                    kind=FailureKind.TEMPORARY,
                )
                if self._record_failure(route_id, route, error):
                    continue
                raise error from None
            except TransportError as exc:
                if self._record_failure(route_id, route, exc):
                    continue
                raise

            first_chunk["model"] = logical_model
            logger.info("route=%s event=success mode=stream committed=true", route_id)

            async def committed_stream(
                first: dict[str, Any] = first_chunk,
                rest: AsyncIterator[dict[str, Any]] = upstream,
                committed_route_id: str = route_id,
            ) -> AsyncIterator[dict[str, Any]]:
                yield first
                try:
                    async for chunk in rest:
                        chunk["model"] = logical_model
                        yield chunk
                except TransportError as exc:
                    logger.error(
                        (
                            "route=%s event=stream_failed_after_commit kind=%s status=%s "
                            "fallback=false"
                        ),
                        committed_route_id,
                        exc.kind,
                        exc.status_code,
                    )
                    raise

            return committed_stream()

        if attempted:
            raise AllRoutesUnavailable("all eligible routes failed before streaming began")
        raise AllRoutesUnavailable("no eligible routes are currently available")
