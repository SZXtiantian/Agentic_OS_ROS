from agentic_runtime.config import RuntimeConfig


def test_config_loads_repo_paths():
    config = RuntimeConfig.load()
    assert config.audit_log_path.name == "audit.jsonl"
    assert config.skill_root.exists()
    assert config.app_root.exists()
