from __future__ import annotations

from typing import Any, Protocol

from free_frontier.models import PhysicalRoute


class TransportError(RuntimeError):
    """A normalized failure while invoking the single Phase 1 upstream route."""


class CompletionTransport(Protocol):
    async def complete(
        self,
        route: PhysicalRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...
