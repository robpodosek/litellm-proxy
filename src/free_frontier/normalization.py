from __future__ import annotations

from typing import Any

_PROVIDER_TOP_LEVEL_PREFIXES = ("x_groq", "x_gemini")


def normalize_response(value: Any, *, top_level: bool = True) -> Any:
    """Remove known top-level provider diagnostics while preserving compatibility metadata."""

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if top_level and key.startswith(_PROVIDER_TOP_LEVEL_PREFIXES):
                continue
            normalized[key] = normalize_response(item, top_level=False)
        return normalized

    if isinstance(value, list):
        return [normalize_response(item, top_level=False) for item in value]

    return value
