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

def test_architecture_constitution_is_wired_into_project_instructions() -> None:
    constitution = (ROOT / "docs" / "CONSTITUTION.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Boring is a feature" in constitution
    assert "No speculative infrastructure" in constitution
    assert "Persistence is earned, not assumed" in constitution
    assert "Presentation stays outside the core" in constitution
    assert "docs/CONSTITUTION.md" in agents
    assert "docs/CONSTITUTION.md" in readme
