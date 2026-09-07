from pathlib import Path

import pytest

from free_frontier.config import ConfigurationError, load_config
from free_frontier.models import AppConfig


def valid_raw_config(*, routes: list[str] | None = None) -> dict:
    return {
        "server": {"host": "127.0.0.1", "port": 4000},
        "routing": {"default_cooldown_seconds": 60},
        "routes": {
            "test-route": {
                "provider": "test",
                "model": "test/physical-model",
                "enabled": True,
                "free": True,
            }
        },
        "logical_models": {
            "free-frontier": {"routes": routes if routes is not None else ["test-route"]}
        },
    }


def test_phase2_config_accepts_ordered_multiple_routes() -> None:
    raw = valid_raw_config(routes=["test-route", "another-route"])
    raw["routes"]["another-route"] = {
        "provider": "test",
        "model": "test/another",
        "enabled": True,
        "free": True,
    }

    config = AppConfig.model_validate(raw)

    assert config.logical_models["free-frontier"].routes == ["test-route", "another-route"]
    assert config.routing.default_cooldown_seconds == 60


def test_config_allows_ineligible_route_but_requires_one_enabled_free_route() -> None:
    raw = valid_raw_config(routes=["paid-route", "test-route"])
    raw["routes"]["paid-route"] = {
        "provider": "test",
        "model": "test/paid",
        "enabled": True,
        "free": False,
    }

    config = AppConfig.model_validate(raw)

    assert config.routes["paid-route"].free is False

    raw["routes"]["test-route"]["enabled"] = False
    with pytest.raises(ValueError, match="at least one enabled free route"):
        AppConfig.model_validate(raw)


def test_unknown_route_reference_is_rejected() -> None:
    raw = valid_raw_config(routes=["missing-route"])
    with pytest.raises(ValueError, match="unknown route 'missing-route'"):
        AppConfig.model_validate(raw)


def test_duplicate_route_reference_is_rejected() -> None:
    raw = valid_raw_config(routes=["test-route", "test-route"])
    with pytest.raises(ValueError, match="must not contain duplicates"):
        AppConfig.model_validate(raw)


def test_load_config_requires_credential_for_each_enabled_free_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "free-frontier.toml"
    config_path.write_text(
        """
[routes.\"first\"]
provider = \"test\"
model = \"test/first\"
enabled = true
free = true
api_key_env = \"FIRST_API_KEY\"

[routes.\"second\"]
provider = \"test\"
model = \"test/second\"
enabled = true
free = true
api_key_env = \"SECOND_API_KEY\"

[logical_models.\"free-frontier\"]
routes = [\"first\", \"second\"]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRST_API_KEY", "secret-first")
    monkeypatch.delenv("SECOND_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(config_path, env_path=None)

    message = str(exc_info.value)
    assert "SECOND_API_KEY" in message
    assert "secret-first" not in message


def test_disabled_route_does_not_require_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "free-frontier.toml"
    config_path.write_text(
        """
[routes.\"enabled\"]
provider = \"test\"
model = \"test/enabled\"
enabled = true
free = true

[routes.\"disabled\"]
provider = \"test\"
model = \"test/disabled\"
enabled = false
free = true
api_key_env = \"MISSING_DISABLED_API_KEY\"

[logical_models.\"free-frontier\"]
routes = [\"enabled\", \"disabled\"]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.delenv("MISSING_DISABLED_API_KEY", raising=False)

    config = load_config(config_path, env_path=None)

    assert config.routes["disabled"].enabled is False


def test_route_rejects_invalid_incompatible_capability_combination() -> None:
    raw = {
        "routes": {
            "route": {
                "provider": "provider",
                "model": "provider/model",
                "enabled": True,
                "free": True,
                "capabilities": ["tools"],
                "incompatible_capability_combinations": [["tools", "structured_output"]],
            }
        },
        "logical_models": {"free-frontier": {"routes": ["route"]}},
    }

    with pytest.raises(ValueError, match="may reference only declared capabilities"):
        AppConfig.model_validate(raw)
