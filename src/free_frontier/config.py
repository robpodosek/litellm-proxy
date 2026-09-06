from __future__ import annotations

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from free_frontier.models import AppConfig

DEFAULT_CONFIG_PATH = Path("free-frontier.toml")
DEFAULT_ENV_PATH = Path(".env")
CONFIG_ENV = "FREE_FRONTIER_CONFIG"


class ConfigurationError(RuntimeError):
    """Raised when Free Frontier cannot safely start from its configuration."""


def load_config(
    path: str | Path | None = None,
    *,
    env_path: str | Path | None = DEFAULT_ENV_PATH,
) -> AppConfig:
    """Load TOML configuration and validate Phase 3 runtime requirements.

    Credential values are never inserted into the typed configuration object. Only the
    environment variable names are retained, which keeps secrets out of reprs/status data.
    """

    if env_path is not None:
        load_dotenv(dotenv_path=env_path, override=False)

    configured_path = path or os.getenv(CONFIG_ENV) or DEFAULT_CONFIG_PATH
    config_path = Path(configured_path)

    if not config_path.is_file():
        raise ConfigurationError(
            f"Free Frontier configuration not found: {config_path}. "
            "Copy free-frontier.toml.example to free-frontier.toml or set "
            f"{CONFIG_ENV}."
        )

    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Could not read {config_path}: {exc}") from exc

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid Free Frontier configuration: {exc}") from exc

    validate_runtime_credentials(config)
    return config


def validate_runtime_credentials(config: AppConfig) -> None:
    """Require credentials only for enabled free routes that Free Frontier may select."""

    logical = config.logical_models["free-frontier"]
    for route_id in logical.routes:
        route = config.routes[route_id]
        if not route.enabled or not route.free:
            continue
        if route.api_key_env and not os.getenv(route.api_key_env):
            raise ConfigurationError(
                f"Route '{route_id}' requires environment variable {route.api_key_env}, "
                "but it is not set. Disable the route or provide its credential."
            )
