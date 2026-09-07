from __future__ import annotations

import logging
import math
import time
from collections.abc import AsyncIterator
from typing import Any

from free_frontier.capabilities import (
    incompatible_capability_combinations,
    missing_capabilities,
    required_capabilities,
)
from free_frontier.cooldowns import CooldownTracker
from free_frontier.models import AppConfig, Capability, PhysicalRoute, RouteDefinition
from free_frontier.normalization import normalize_response
from free_frontier.observability import ObservabilityState
from free_frontier.providers.base import CompletionTransport, FailureKind, TransportError

logger = logging.getLogger("uvicorn.error.free_frontier.routing")


class UnknownLogicalModel(LookupError):
    pass


class AllRoutesUnavailable(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


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
        observability: ObservabilityState | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._cooldowns = cooldowns or CooldownTracker()
        self._observability = observability or ObservabilityState(config.routes)

    @property
    def observability(self) -> ObservabilityState:
        return self._observability

    def logical_models(self) -> list[str]:
        return sorted(self._config.logical_models)

    def cooldown_remaining(self, route_id: str) -> float:
        """Read current cooldown state without changing routing policy."""

        return self._cooldowns.remaining(route_id)

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
            incompatible_capability_combinations=(
                route.incompatible_capability_combinations
            ),
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

    def _compatibility_issue(
        self,
        route: RouteDefinition,
        required: frozenset[Capability],
    ) -> tuple[str, str] | None:
        missing = missing_capabilities(route.capabilities, required)
        if missing:
            names = ",".join(sorted(capability.value for capability in missing))
            return "capability", names

        combinations = incompatible_capability_combinations(
            route.incompatible_capability_combinations,
            required,
        )
        if combinations:
            first = combinations[0]
            names = "+".join(sorted(capability.value for capability in first))
            return "capability_combination", names

        return None

    def _logical_routes(
        self,
        logical_model: str,
        payload: dict[str, Any],
        *,
        request_id: str,
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
                logger.info(
                    "request=%s route=%s event=skipped reason=ineligible",
                    request_id,
                    route_id,
                )
                self._observability.record_route_skip(route_id, "ineligible")
                continue

            eligible_free_seen = True
            issue = self._compatibility_issue(route, required)
            if issue is not None:
                reason, detail = issue
                logger.info(
                    "request=%s route=%s event=skipped reason=%s detail=%s",
                    request_id,
                    route_id,
                    reason,
                    detail,
                )
                self._observability.record_route_skip(route_id, f"{reason}:{detail}")
                continue

            compatible.append((route_id, route))

        if eligible_free_seen and not compatible:
            raise NoCompatibleRoutes(required)

        return compatible, required

    def _available_routes(
        self,
        logical_model: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> list[tuple[str, RouteDefinition]]:
        compatible, _ = self._logical_routes(
            logical_model,
            payload,
            request_id=request_id,
        )
        available: list[tuple[str, RouteDefinition]] = []

        for route_id, route in compatible:
            remaining = self._cooldowns.remaining(route_id)
            if remaining > 0:
                logger.info(
                    "request=%s route=%s event=skipped reason=cooldown remaining=%.1f",
                    request_id,
                    route_id,
                    remaining,
                )
                self._observability.record_route_skip(route_id, "cooldown")
                continue
            available.append((route_id, route))

        return available

    def _retry_after_seconds(
        self,
        logical_model: str,
        payload: dict[str, Any],
    ) -> int | None:
        logical = self._config.logical_models.get(logical_model)
        if logical is None:
            return None

        required = required_capabilities(payload)
        remaining_values: list[float] = []
        for route_id in logical.routes:
            route = self._config.routes[route_id]
            if not route.enabled or not route.free:
                continue
            if self._compatibility_issue(route, required) is not None:
                continue
            remaining = self._cooldowns.remaining(route_id)
            if remaining > 0:
                remaining_values.append(remaining)

        if not remaining_values:
            return None
        return max(1, math.ceil(min(remaining_values)))

    def _unavailable(
        self,
        logical_model: str,
        payload: dict[str, Any],
        message: str,
    ) -> AllRoutesUnavailable:
        return AllRoutesUnavailable(
            message,
            retry_after_seconds=self._retry_after_seconds(logical_model, payload),
        )

    def _record_failure(
        self,
        route_id: str,
        route: RouteDefinition,
        error: TransportError,
        *,
        latency_ms: float,
        request_id: str,
    ) -> bool:
        if not error.fallback_worthy:
            logger.error(
                "request=%s route=%s event=failed kind=%s status=%s fallback=false",
                request_id,
                route_id,
                error.kind,
                error.status_code,
            )
            self._observability.record_route_failure(
                route_id,
                kind=error.kind.value,
                status_code=error.status_code,
                latency_ms=latency_ms,
                fallback=False,
            )
            return False

        cooldown_seconds = self._cooldown_seconds(route, error)
        self._cooldowns.start(route_id, cooldown_seconds)
        logger.warning(
            (
                "request=%s route=%s event=failed kind=%s status=%s "
                "fallback=true cooldown=%.1f"
            ),
            request_id,
            route_id,
            error.kind,
            error.status_code,
            cooldown_seconds,
        )
        self._observability.record_route_failure(
            route_id,
            kind=error.kind.value,
            status_code=error.status_code,
            latency_ms=latency_ms,
            fallback=True,
        )
        return True

    async def complete(
        self,
        logical_model: str,
        payload: dict[str, Any],
        *,
        request_id: str = "-",
    ) -> dict[str, Any]:
        attempted = False

        for route_id, route in self._available_routes(
            logical_model,
            payload,
            request_id=request_id,
        ):
            attempted = True
            physical = self._physical_route(route_id, route)
            started = time.perf_counter()
            self._observability.record_route_attempt(route_id)
            logger.info(
                "request=%s route=%s event=attempt mode=completion",
                request_id,
                route_id,
            )

            try:
                response = await self._transport.complete(physical, payload)
            except TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                if self._record_failure(
                    route_id,
                    route,
                    exc,
                    latency_ms=latency_ms,
                    request_id=request_id,
                ):
                    continue
                raise

            latency_ms = (time.perf_counter() - started) * 1000
            self._observability.record_route_selected(route_id)
            self._observability.record_route_success(route_id, latency_ms=latency_ms)
            logger.info(
                "request=%s route=%s event=success mode=completion",
                request_id,
                route_id,
            )
            response = normalize_response(response)
            response["model"] = logical_model
            return response

        if attempted:
            raise self._unavailable(logical_model, payload, "all eligible routes failed")
        raise self._unavailable(
            logical_model,
            payload,
            "no eligible routes are currently available",
        )

    async def stream(
        self,
        logical_model: str,
        payload: dict[str, Any],
        *,
        request_id: str = "-",
    ) -> AsyncIterator[dict[str, Any]]:
        """Start a stream, allowing fallback only before the first upstream chunk."""

        attempted = False

        for route_id, route in self._available_routes(
            logical_model,
            payload,
            request_id=request_id,
        ):
            attempted = True
            physical = self._physical_route(route_id, route)
            started = time.perf_counter()
            self._observability.record_route_attempt(route_id)
            logger.info(
                "request=%s route=%s event=attempt mode=stream",
                request_id,
                route_id,
            )

            try:
                upstream = await self._transport.stream(physical, payload)
                first_chunk = await anext(upstream)
            except StopAsyncIteration:
                error = TransportError(
                    "upstream stream ended before producing a chunk",
                    kind=FailureKind.TEMPORARY,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                if self._record_failure(
                    route_id,
                    route,
                    error,
                    latency_ms=latency_ms,
                    request_id=request_id,
                ):
                    continue
                raise error from None
            except TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                if self._record_failure(
                    route_id,
                    route,
                    exc,
                    latency_ms=latency_ms,
                    request_id=request_id,
                ):
                    continue
                raise

            first_chunk = normalize_response(first_chunk)
            first_chunk["model"] = logical_model
            self._observability.record_route_selected(route_id)
            logger.info(
                "request=%s route=%s event=success mode=stream committed=true",
                request_id,
                route_id,
            )

            async def committed_stream(
                first: dict[str, Any] = first_chunk,
                rest: AsyncIterator[dict[str, Any]] = upstream,
                committed_route_id: str = route_id,
                attempt_started: float = started,
                committed_request_id: str = request_id,
            ) -> AsyncIterator[dict[str, Any]]:
                yield first
                try:
                    async for chunk in rest:
                        chunk = normalize_response(chunk)
                        chunk["model"] = logical_model
                        yield chunk
                except TransportError as exc:
                    latency_ms = (time.perf_counter() - attempt_started) * 1000
                    self._observability.record_route_failure(
                        committed_route_id,
                        kind=exc.kind.value,
                        status_code=exc.status_code,
                        latency_ms=latency_ms,
                        fallback=False,
                    )
                    logger.error(
                        (
                            "request=%s route=%s event=stream_failed_after_commit "
                            "kind=%s status=%s fallback=false"
                        ),
                        committed_request_id,
                        committed_route_id,
                        exc.kind,
                        exc.status_code,
                    )
                    raise

                latency_ms = (time.perf_counter() - attempt_started) * 1000
                self._observability.record_route_success(
                    committed_route_id,
                    latency_ms=latency_ms,
                )

            return committed_stream()

        if attempted:
            raise self._unavailable(
                logical_model,
                payload,
                "all eligible routes failed before streaming began",
            )
        raise self._unavailable(
            logical_model,
            payload,
            "no eligible routes are currently available",
        )
