#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


RUNTIME_SRC = Path(__file__).resolve().parent.parent
SOURCE_OS = RUNTIME_SRC / "agentic_os"
SOURCE_RUNTIME_DUPLICATE = RUNTIME_SRC / "agentic_runtime" / "agentic_os"

ALLOWED_TOP_LEVEL_DIRS = {
    "agentic_os",
    "bin",
    "bridges",
    "docs",
    "etc",
    "lib",
    "sdk",
    "skills",
    "tests",
    "var",
}
ALLOWED_TOP_LEVEL_FILES = {"README.md", "setup.bash", "pytest.ini"}
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache"}
LEGACY_KERNEL_NAMES = {
    "memory_mngt",
    "context_mngt",
    "tool_mngt",
    "agent_scheduler",
    "agent_friendly_perception",
    "side_model_library",
}
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


def install_root() -> Path:
    opt = Path("/opt/agentic")
    if opt.exists():
        return opt
    return Path("/home/ubuntu/staging_opt_agentic")


def validate_kernel_code(root: Path, label: str, failures: list[str]) -> None:
    package_init = root / "agentic_os" / "__init__.py"
    kernel_init = root / "agentic_os" / "kernel" / "__init__.py"
    for path in [package_init, kernel_init]:
        if not path.is_file():
            failures.append(f"missing {label} import package file: {path}")
    for module_name, files in KERNEL_CODE_FILES.items():
        module_dir = root / "agentic_os" / "kernel" / module_name
        if not module_dir.is_dir():
            failures.append(f"missing {label} kernel source directory: {module_dir}")
            continue
        py_files = [path for path in module_dir.glob("*.py") if path.is_file()]
        if not py_files:
            failures.append(f"{label} kernel module has no Python source files: {module_dir}")
        for filename in files:
            path = module_dir / filename
            if not path.is_file():
                failures.append(f"missing {label} kernel source file: {path}")


def main() -> int:
    failures: list[str] = []

    if not SOURCE_OS.exists():
        failures.append(f"missing source AgenticOS kernel tree: {SOURCE_OS}")
    if SOURCE_RUNTIME_DUPLICATE.exists():
        failures.append(f"runtime source must not contain AgenticOS kernel tree: {SOURCE_RUNTIME_DUPLICATE}")
    for name in CANONICAL_KERNEL_DIRS:
        path = SOURCE_OS / "kernel" / name
        if not path.is_dir():
            failures.append(f"missing source kernel directory: {path}")
    validate_kernel_code(RUNTIME_SRC, "source", failures)
    for name in LEGACY_KERNEL_NAMES:
        path = SOURCE_OS / "kernel" / name
        if path.exists():
            failures.append(f"legacy source kernel contract directory must not exist: {path}")
    source_models = RUNTIME_SRC / "configs" / "models.yaml"
    if source_models.exists() and "side_model_library" in source_models.read_text(encoding="utf-8"):
        failures.append(f"source models config references legacy side_model_library: {source_models}")

    root = install_root()
    if not root.exists():
        failures.append(f"missing install root: {root}")
    else:
        for child in root.iterdir():
            if child.name in ALLOWED_TOP_LEVEL_DIRS:
                if not child.is_dir():
                    failures.append(f"expected top-level directory but found non-directory: {child}")
            elif child.name in ALLOWED_TOP_LEVEL_FILES:
                if not child.is_file():
                    failures.append(f"expected top-level file but found non-file: {child}")
            else:
                failures.append(f"unexpected top-level AgenticOS entry: {child}")

        for path in root.rglob("*"):
            if path.is_dir() and path.name in CACHE_DIR_NAMES:
                failures.append(f"generated cache directory must not exist in install root: {path}")

        installed_duplicate = root / "lib" / "python3" / "agentic_runtime" / "agentic_os"
        required_dirs = [
            root / "agentic_os",
            root / "agentic_os" / "hardware",
            root / "bridges" / "ros2",
            root / "etc" / "bridge_profiles",
            root / "lib" / "python3" / "agentic_runtime",
            root / "sdk" / "python",
            root / "sdk" / "cpp",
            root / "skills",
            root / "tests",
            root / "docs",
            root / "var" / "audit",
            root / "var" / "memory",
            root / "var" / "sessions",
        ]
        if installed_duplicate.exists():
            failures.append(f"installed runtime duplicate tree must not exist: {installed_duplicate}")
        for path in required_dirs:
            if not path.is_dir():
                failures.append(f"required AgenticOS layout directory missing: {path}")
        if (root / "hardware").exists():
            failures.append(f"deprecated top-level hardware directory must not exist: {root / 'hardware'}")
        for name in CANONICAL_KERNEL_DIRS:
            path = root / "agentic_os" / "kernel" / name
            if not path.is_dir():
                failures.append(f"missing installed kernel directory: {path}")
        validate_kernel_code(root, "installed", failures)
        for name in LEGACY_KERNEL_NAMES:
            path = root / "agentic_os" / "kernel" / name
            if path.exists():
                failures.append(f"legacy installed kernel contract directory must not exist: {path}")
        for path in [root / "README.md", root / "setup.bash", root / "pytest.ini"]:
            if not path.is_file():
                failures.append(f"required AgenticOS root file missing: {path}")
        installed_models = root / "etc" / "models.yaml"
        if installed_models.exists() and "side_model_library" in installed_models.read_text(encoding="utf-8"):
            failures.append(f"installed models config references legacy side_model_library: {installed_models}")

    if failures:
        print("filesystem layout guard failed:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("filesystem layout guard ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
