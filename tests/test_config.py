from pathlib import Path

import pytest

from free_frontier.config import ConfigurationError, load_config
from free_frontier.models import AppConfig


def valid_raw_config(*, free: bool = True, routes: list[str] | None = None) -> dict:
    return {
        "server": {"host": "127.0.0.1", "port": 4000},
        "routes": {
            "test-route": {
                "provider": "test",
                "model": "test/physical-model",
                "enabled": True,
                "free": free,
            }
        },
        "logical_models": {
            "free-frontier": {"routes": routes if routes is not None else ["test-route"]}
        },
    }


def test_phase1_config_resolves_one_free_route() -> None:
    config = AppConfig.model_validate(valid_raw_config())
    assert config.logical_models["free-frontier"].routes == ["test-route"]
    assert config.routes["test-route"].free is True


def test_phase1_rejects_multiple_routes_until_phase2() -> None:
    raw = valid_raw_config(routes=["test-route", "another-route"])
    raw["routes"]["another-route"] = {
        "provider": "test",
        "model": "test/another",
        "enabled": True,
        "free": True,
    }

    with pytest.raises(ValueError, match="exactly one route"):
        AppConfig.model_validate(raw)


def test_free_only_policy_rejects_paid_route() -> None:
    with pytest.raises(ValueError, match="free-only policy"):
        AppConfig.model_validate(valid_raw_config(free=False))


def test_unknown_route_reference_is_rejected() -> None:
    raw = valid_raw_config(routes=["missing-route"])
    with pytest.raises(ValueError, match="unknown route 'missing-route'"):
        AppConfig.model_validate(raw)


def test_load_config_requires_declared_credential_without_leaking_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "free-frontier.toml"
    config_path.write_text(
        """
[routes.\"test-route\"]
provider = \"test\"
model = \"test/model\"
enabled = true
free = true
api_key_env = \"TEST_PROVIDER_API_KEY\"

[logical_models.\"free-frontier\"]
routes = [\"test-route\"]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_PROVIDER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(config_path, env_path=None)

    message = str(exc_info.value)
    assert "TEST_PROVIDER_API_KEY" in message
    assert "api_key" not in message.lower().replace("test_provider_api_key", "")
