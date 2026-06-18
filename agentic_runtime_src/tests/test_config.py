from agentic_runtime.config import RuntimeConfig, find_repo_root


def test_config_loads_repo_paths():
    config = RuntimeConfig.load()
    assert config.audit_log_path.name == "audit.jsonl"
    assert config.skill_root.exists()
    assert config.app_root.exists()


def test_find_repo_root_from_repo_runtime_and_app_dirs(repo_root, runtime_src, app_root):
    assert find_repo_root(repo_root) == runtime_src
    assert find_repo_root(runtime_src) == runtime_src
    assert find_repo_root(app_root) == runtime_src


def test_default_runtime_config_is_repo_relative(runtime_src, app_root):
    config = RuntimeConfig.load()

    assert config.repo_root == runtime_src
    assert config.app_root == app_root
    assert config.skill_root == runtime_src / "skills"
    assert str(config.app_root) != "/home/ubuntu/agentic_ws/src"
    assert str(config.skill_root) != "/home/ubuntu/agentic_ws/src/agentic_runtime_src/skills"


def test_runtime_config_loads_kernel_block():
    config = RuntimeConfig.load()

    assert config.kernel["scheduler_policy"] == "fifo"
    assert config.kernel["llm"]["configs"][0]["name"] == "mock-kernel"
    assert config.kernel["tool"]["mcp_enabled"] is False
