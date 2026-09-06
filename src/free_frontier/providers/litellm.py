from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from typing import Any

from free_frontier.models import PhysicalRoute
from free_frontier.providers.base import FailureKind, TransportError

_TEMPORARY_STATUS_CODES = {408, 425, 500, 502, 503, 504, 529}
_TEMPORARY_EXCEPTION_NAMES = {
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
    "Timeout",
    "TimeoutError",
}
_ROUTE_UNAVAILABLE_STATUS_CODES = {404}


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers: Mapping[str, Any] | None = getattr(response, "headers", None)
    if headers is None:
        possible_headers = getattr(exc, "headers", None)
        if isinstance(possible_headers, Mapping):
            headers = possible_headers
    if headers is None:
        return None

    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)


def _classify_exception(exc: Exception) -> tuple[FailureKind, int | None, float | None]:
    status = _status_code(exc)
    name = type(exc).__name__
    retry_after = _retry_after_seconds(exc)

    if status == 429 or name == "RateLimitError":
        return FailureKind.RATE_LIMIT, status, retry_after
    if status in _ROUTE_UNAVAILABLE_STATUS_CODES or name == "NotFoundError":
        return FailureKind.ROUTE_UNAVAILABLE, status, retry_after
    if status in _TEMPORARY_STATUS_CODES or name in _TEMPORARY_EXCEPTION_NAMES:
        return FailureKind.TEMPORARY, status, retry_after
    return FailureKind.NON_RETRYABLE, status, retry_after


def _transport_error(route: PhysicalRoute, exc: Exception) -> TransportError:
    kind, status, retry_after = _classify_exception(exc)
    return TransportError(
        f"Upstream route '{route.id}' failed via provider '{route.provider}'",
        kind=kind,
        status_code=status,
        retry_after_seconds=retry_after,
    )


def _as_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return dict(response)
    if hasattr(response, "model_dump"):
        return response.model_dump()

    try:
        return dict(response)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive adapter guard
        raise TransportError("LiteLLM returned an unsupported response type") from exc


class LiteLLMTransport:
    """Provider-normalization transport backed by LiteLLM's Python SDK."""

    def _kwargs(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
        *,
        stream: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            **payload,
            **route.litellm_params,
            "model": route.model,
            "stream": stream,
        }
        if route.api_key_env:
            api_key = os.getenv(route.api_key_env)
            if not api_key:
                raise TransportError(
                    f"Credential environment variable {route.api_key_env} is not set"
                )
            kwargs["api_key"] = api_key
        if route.api_base:
            kwargs["api_base"] = route.api_base
        return kwargs

    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - packaging/runtime guard
            raise TransportError("LiteLLM is not installed") from exc

        kwargs = self._kwargs(route, payload, stream=False)

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise _transport_error(route, exc) from exc

        return _as_dict(response)

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - packaging/runtime guard
            raise TransportError("LiteLLM is not installed") from exc

        kwargs = self._kwargs(route, payload, stream=True)

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise _transport_error(route, exc) from exc

        if not hasattr(response, "__aiter__"):
            raise TransportError("LiteLLM returned a non-streaming response for stream=true")

        async def chunks() -> AsyncIterator[dict[str, Any]]:
            try:
                async for chunk in response:
                    yield _as_dict(chunk)
            except TransportError:
                raise
            except Exception as exc:
                raise _transport_error(route, exc) from exc

        return chunks()
