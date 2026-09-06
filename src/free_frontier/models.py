from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_FORBIDDEN_LITELLM_PARAMS = {"api_key", "messages", "model", "stream"}


class Capability(StrEnum):
    STREAMING = "streaming"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=4000, ge=1, le=65535)


class RoutingConfig(BaseModel):
    """Global Phase 4 routing policy."""

    model_config = ConfigDict(extra="forbid")

    default_cooldown_seconds: float = Field(default=60.0, ge=0.0, le=86400.0)


class RouteDefinition(BaseModel):
    """One concrete provider/model route behind a logical model."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    enabled: bool = True
    free: bool
    capabilities: frozenset[Capability] = Field(default_factory=frozenset)
    api_key_env: str | None = None
    api_base: str | None = None
    cooldown_seconds: float | None = Field(default=None, ge=0.0, le=86400.0)
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

    @model_validator(mode="after")
    def validate_route_order(self) -> LogicalModelDefinition:
        if len(self.routes) != len(set(self.routes)):
            raise ValueError("logical model routes must not contain duplicates")
        return self


class AppConfig(BaseModel):
    """Validated Free Frontier configuration for Phase 4."""

    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    routes: dict[str, RouteDefinition]
    logical_models: dict[str, LogicalModelDefinition]

    @model_validator(mode="after")
    def validate_phase3_contract(self) -> AppConfig:
        logical = self.logical_models.get("free-frontier")
        if logical is None:
            raise ValueError("logical_models must define 'free-frontier'")

        for route_id in logical.routes:
            if route_id not in self.routes:
                raise ValueError(
                    f"logical model 'free-frontier' references unknown route '{route_id}'"
                )

        if not any(
            self.routes[route_id].enabled and self.routes[route_id].free
            for route_id in logical.routes
        ):
            raise ValueError(
                "logical model 'free-frontier' must reference at least one enabled free route"
            )
        return self


@dataclass(frozen=True, slots=True)
class PhysicalRoute:
    id: str
    provider: str
    model: str
    capabilities: frozenset[Capability]
    api_key_env: str | None
    api_base: str | None
    litellm_params: dict[str, Any]
