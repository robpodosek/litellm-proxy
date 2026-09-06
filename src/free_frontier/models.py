from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_FORBIDDEN_LITELLM_PARAMS = {"api_key", "messages", "model", "stream"}


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=4000, ge=1, le=65535)


class RouteDefinition(BaseModel):
    """One concrete provider/model route.

    Route IDs live in the surrounding configuration mapping. Provider/model identities
    are internal details and are never required from normal Free Frontier clients.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    enabled: bool = True
    free: bool
    api_key_env: str | None = None
    api_base: str | None = None
    litellm_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_route(self) -> RouteDefinition:
        if self.api_key_env is not None and not _ENV_NAME_RE.fullmatch(self.api_key_env):
            raise ValueError("api_key_env must be an uppercase environment variable name")

        forbidden = _FORBIDDEN_LITELLM_PARAMS.intersection(self.litellm_params)
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ValueError(f"litellm_params cannot override protected fields: {names}")
        return self


class LogicalModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routes: list[str] = Field(min_length=1)


class AppConfig(BaseModel):
    """Validated Free Frontier configuration for Phase 1."""

    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    routes: dict[str, RouteDefinition]
    logical_models: dict[str, LogicalModelDefinition]

    @model_validator(mode="after")
    def validate_phase1_contract(self) -> AppConfig:
        logical = self.logical_models.get("free-frontier")
        if logical is None:
            raise ValueError("logical_models must define 'free-frontier'")

        # Phase 1 intentionally proves the abstraction with one route. Phase 2 removes
        # this restriction and adds ordered selection, fallback, and cooldowns.
        if len(logical.routes) != 1:
            raise ValueError("Phase 1 requires 'free-frontier' to reference exactly one route")

        route_id = logical.routes[0]
        route = self.routes.get(route_id)
        if route is None:
            raise ValueError(f"logical model 'free-frontier' references unknown route '{route_id}'")
        if not route.enabled:
            raise ValueError(f"route '{route_id}' referenced by 'free-frontier' is disabled")
        if not route.free:
            raise ValueError(f"route '{route_id}' is not eligible under the v0.1 free-only policy")
        return self


@dataclass(frozen=True, slots=True)
class PhysicalRoute:
    id: str
    provider: str
    model: str
    api_key_env: str | None
    api_base: str | None
    litellm_params: dict[str, Any]
