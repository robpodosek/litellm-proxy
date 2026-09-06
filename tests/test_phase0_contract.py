from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_runtime_files_are_removed() -> None:
    for relative_path in (
        "main.py",
        "monitor.py",
        "proxy_callbacks.py",
        "config.yaml",
        "stats.json",
        "proxy.log",
        "Dockerfile",
        "docker-compose.yml",
    ):
        assert not (ROOT / relative_path).exists(), f"legacy Phase 0 file remains: {relative_path}"


def test_product_contract_uses_logical_model() -> None:
    spec = (ROOT / "docs" / "SPEC-v0.1.md").read_text(encoding="utf-8")
    assert "free-frontier" in spec
    assert "MUST NOT knowingly route" in spec
    assert "does not implement agents" in spec


def test_agent_instructions_preserve_product_boundary() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Free Frontier is **not** an agent framework" in agents
    assert "v0.1 is free-only" in agents
    assert "Monitoring data belongs in the core" in agents
