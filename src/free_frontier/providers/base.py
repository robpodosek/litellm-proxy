from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any, Protocol

from free_frontier.models import PhysicalRoute


class FailureKind(StrEnum):
    """Safe, provider-agnostic transport failure categories used by routing policy."""

    RATE_LIMIT = "rate_limit"
    TEMPORARY = "temporary"
    ROUTE_UNAVAILABLE = "route_unavailable"
    NON_RETRYABLE = "non_retryable"


_FALLBACK_WORTHY = {
    FailureKind.RATE_LIMIT,
    FailureKind.TEMPORARY,
    FailureKind.ROUTE_UNAVAILABLE,
}


class TransportError(RuntimeError):
    """A normalized upstream failure that does not expose provider secrets."""

    def __init__(
        self,
        message: str,
        *,
        kind: FailureKind = FailureKind.NON_RETRYABLE,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    @property
    def fallback_worthy(self) -> bool:
        return self.kind in _FALLBACK_WORTHY


class CompletionTransport(Protocol):
    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def stream(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]: ...
