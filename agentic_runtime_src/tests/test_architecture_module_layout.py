import os
from pathlib import Path


RUNTIME_SRC = Path(os.environ["AGENTIC_RUNTIME_SRC"])
SOURCE_ROOT = RUNTIME_SRC / "agentic_os"
RUNTIME_DUPLICATE = RUNTIME_SRC / "agentic_runtime" / "agentic_os"
CANONICAL_KERNEL_DIRS = [
    "system_call",
    "capability",
    "skill_library",
    "memory",
    "model_library",
    "context",
    "tool",
    "storage",
    "scheduler",
    "perception",
    "device_arbitration",
    "world_model",
]
KERNEL_CODE_FILES = {
    "system_call": ["__init__.py", "models.py", "executor.py"],
    "capability": ["__init__.py", "registry.py"],
    "skill_library": ["__init__.py", "registry.py"],
    "memory": ["__init__.py", "manager.py"],
    "model_library": ["__init__.py", "router.py"],
    "context": ["__init__.py", "manager.py"],
    "tool": ["__init__.py", "manager.py"],
    "storage": ["__init__.py", "manager.py"],
    "scheduler": ["__init__.py", "scheduler.py"],
    "perception": ["__init__.py", "manager.py"],
    "device_arbitration": ["__init__.py", "arbiter.py"],
    "world_model": ["__init__.py", "manager.py"],
}
LEGACY_KERNEL_DIRS = [
    "memory_mngt",
    "context_mngt",
    "tool_mngt",
    "agent_scheduler",
    "agent_friendly_perception",
    "side_model_library",
]
ALLOWED_TOP_LEVEL_DIRS = {
    "agentic_os",
    "bin",
    "bridges",
    "docs",
    "etc",
    "lib",
    "sdk",
    "system_skills",
    "tests",
    "var",
}
ALLOWED_TOP_LEVEL_FILES = {"README.md", "setup.bash", "pytest.ini"}


def install_root(tmp_path: Path, runtime_src: Path) -> Path:
    configured = os.environ.get("AGENTIC_INSTALL_ROOT")
    if configured:
        return Path(configured).expanduser()
    root = tmp_path / "staging_opt_agentic"
    _fake_install_root(root, runtime_src)
    return root


def test_source_architecture_modules_exist():
    for name in CANONICAL_KERNEL_DIRS:
        assert (SOURCE_ROOT / "kernel" / name).exists()
    for relative in [
        "security/model_security",
        "security/system_security",
        "security/sensor_actuator_security",
    ]:
        assert (SOURCE_ROOT / relative).exists()


def test_runtime_source_does_not_embed_architecture_modules():
    assert not RUNTIME_DUPLICATE.exists()


def test_source_kernel_modules_have_importable_code_files():
    assert (SOURCE_ROOT / "__init__.py").is_file()
    assert (SOURCE_ROOT / "kernel" / "__init__.py").is_file()
    for module_name, files in KERNEL_CODE_FILES.items():
        module_dir = SOURCE_ROOT / "kernel" / module_name
        assert any(path.suffix == ".py" for path in module_dir.iterdir())
        for filename in files:
            assert (module_dir / filename).is_file()


def test_source_architecture_modules_use_canonical_names():
    for name in LEGACY_KERNEL_DIRS:
        assert not (SOURCE_ROOT / "kernel" / name).exists()


def test_install_architecture_modules_exist(tmp_path, runtime_src):
    root = install_root(tmp_path, runtime_src) / "agentic_os"
    for name in CANONICAL_KERNEL_DIRS:
        assert (root / "kernel" / name).exists()
    for relative in [
        "hardware",
        "security/model_security",
        "security/system_security",
        "security/sensor_actuator_security",
    ]:
        assert (root / relative).exists()


def test_installed_runtime_does_not_embed_architecture_modules(tmp_path, runtime_src):
    duplicate = install_root(tmp_path, runtime_src) / "lib" / "python3" / "agentic_runtime" / "agentic_os"
    assert not duplicate.exists()


def test_installed_kernel_modules_have_importable_code_files(tmp_path, runtime_src):
    root = install_root(tmp_path, runtime_src) / "agentic_os"
    assert (root / "__init__.py").is_file()
    assert (root / "kernel" / "__init__.py").is_file()
    for module_name, files in KERNEL_CODE_FILES.items():
        module_dir = root / "kernel" / module_name
        assert any(path.suffix == ".py" for path in module_dir.iterdir())
        for filename in files:
            assert (module_dir / filename).is_file()


def test_install_architecture_modules_use_canonical_names(tmp_path, runtime_src):
    root = install_root(tmp_path, runtime_src) / "agentic_os"
    for name in LEGACY_KERNEL_DIRS:
        assert not (root / "kernel" / name).exists()


def test_install_root_top_level_contract_is_strict(tmp_path, runtime_src):
    root = install_root(tmp_path, runtime_src)
    assert root.exists()
    for child in root.iterdir():
        assert child.name in ALLOWED_TOP_LEVEL_DIRS | ALLOWED_TOP_LEVEL_FILES


def test_install_root_has_no_generated_cache_directories(tmp_path, runtime_src):
    root = install_root(tmp_path, runtime_src)
    assert not any(path.name in {"__pycache__", ".pytest_cache"} for path in root.rglob("*") if path.is_dir())


def test_models_config_uses_canonical_model_library_path(tmp_path, runtime_src):
    source_models = runtime_src / "configs" / "models.yaml"
    installed_models = install_root(tmp_path, runtime_src) / "etc" / "models.yaml"
    assert "side_model_library" not in source_models.read_text(encoding="utf-8")
    assert "side_model_library" not in installed_models.read_text(encoding="utf-8")


def _fake_install_root(root: Path, runtime_src: Path) -> None:
    for relative in [
        "bin",
        "bridges/ros2",
        "docs",
        "etc/robot_profiles",
        "lib/python3/agentic_runtime",
        "sdk",
        "system_skills",
        "tests",
        "var",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    source = runtime_src / "agentic_os"
    for relative in ["__init__.py", "kernel/__init__.py"]:
        _copy_text(source / relative, root / "agentic_os" / relative)
    for module_name, files in KERNEL_CODE_FILES.items():
        for filename in files:
            _copy_text(source / "kernel" / module_name / filename, root / "agentic_os" / "kernel" / module_name / filename)
    for relative in [
        "hardware",
        "security/model_security",
        "security/system_security",
        "security/sensor_actuator_security",
    ]:
        (root / "agentic_os" / relative).mkdir(parents=True, exist_ok=True)
    _copy_text(runtime_src / "configs" / "models.yaml", root / "etc" / "models.yaml")


def _copy_text(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
