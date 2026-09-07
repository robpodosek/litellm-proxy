from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from free_frontier.models import Capability

_TOOL_REQUEST_KEYS = {
    "function_call",
    "functions",
    "parallel_tool_calls",
    "tool_choice",
    "tools",
}


def required_capabilities(payload: Mapping[str, Any]) -> frozenset[Capability]:
    """Infer route capabilities required by an OpenAI-compatible chat request."""

    required: set[Capability] = set()

    if payload.get("stream") is True:
        required.add(Capability.STREAMING)

    if any(payload.get(key) is not None for key in _TOOL_REQUEST_KEYS):
        required.add(Capability.TOOLS)

    response_format = payload.get("response_format")
    if isinstance(response_format, Mapping) and response_format.get("type") not in {None, "text"}:
        required.add(Capability.STRUCTURED_OUTPUT)

    if _messages_include_images(payload.get("messages")):
        required.add(Capability.VISION)

    return frozenset(required)


def missing_capabilities(
    supported: frozenset[Capability],
    required: frozenset[Capability],
) -> frozenset[Capability]:
    return required.difference(supported)


def _messages_include_images(messages: Any) -> bool:
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes, bytearray)):
        return False

    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            if part.get("type") in {"image_url", "input_image", "image"}:
                return True
    return False


def incompatible_capability_combinations(
    configured: tuple[frozenset[Capability], ...],
    required: frozenset[Capability],
) -> tuple[frozenset[Capability], ...]:
    """Return declared route restrictions triggered by the request."""

    return tuple(
        combination for combination in configured if combination.issubset(required)
    )
