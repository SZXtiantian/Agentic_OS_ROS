from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def find_repo_root(start: Path | None = None) -> Path:
    env_src = os.environ.get("AGENTIC_RUNTIME_SRC")
    if env_src:
        return Path(env_src).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "agentic_runtime_src" / "agentic_runtime").is_dir():
            return candidate / "agentic_runtime_src"
        if (candidate / "agentic_runtime").is_dir() and (candidate / "configs").is_dir():
            return candidate
    return current


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass(frozen=True)
class RuntimeConfig:
    repo_root: Path
    audit_log_path: Path
    memory_db_path: Path
    default_skill_timeout_s: int
    app_root: Path
    skill_root: Path
    ros_bridge_mode: str = "cli"
    daemon_host: str = "127.0.0.1"
    daemon_port: int = 8765
    session_root: Path = Path("/opt/agentic/var/sessions")
    storage_root: Path = Path("/opt/agentic/var/storage")
    context_root: Path = Path("/opt/agentic/var/context")
    scheduler_policy: str = "single_robot_fifo"
    memory_provider: str = "sqlite"
    tool_root: Path = Path("/opt/agentic/tools")
    bridge_root: Path = Path("/opt/agentic/bridges/ros2")
    bridge_profile_root: Path = Path("/opt/agentic/etc/bridge_profiles")
    enable_daemon_api: bool = True
    kernel: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "RuntimeConfig":
        repo_root = find_repo_root()
        agentic_home = Path(os.environ.get("AGENTIC_HOME", "/opt/agentic")).expanduser()

        env_runtime_src = Path(os.environ["AGENTIC_RUNTIME_SRC"]).expanduser() if os.environ.get("AGENTIC_RUNTIME_SRC") else None
        path = _first_existing(
            [
                Path(config_path).expanduser() if config_path else None,
                Path(os.environ["AGENTIC_RUNTIME_CONFIG"]).expanduser()
                if os.environ.get("AGENTIC_RUNTIME_CONFIG")
                else None,
                env_runtime_src / "configs" / "runtime.yaml" if env_runtime_src else None,
                repo_root / "configs" / "runtime.yaml",
                agentic_home / "etc" / "agentic.yaml" if os.environ.get("AGENTIC_HOME") else None,
            ]
        )
        raw_data = load_yaml(path) if path else {}
        data = raw_data.get("runtime", {})
        kernel_data = raw_data.get("kernel", {})
        config_base = _config_base(path, repo_root, agentic_home)

        def resolve(value: str | None, default: Path | str, base: Path = config_base) -> Path:
            raw = Path(value or default)
            if raw.is_absolute():
                return raw
            return (base / raw).resolve()

        app_root_default = Path(os.environ.get("AGENTIC_APP_ROOT", repo_root.parent))
        skill_root_default = Path(os.environ.get("AGENTIC_SKILLS", repo_root / "skills"))
        var_root = Path(os.environ.get("AGENTIC_VAR", agentic_home / "var"))
        etc_root = Path(os.environ.get("AGENTIC_ETC", agentic_home / "etc"))

        return cls(
            repo_root=repo_root,
            audit_log_path=resolve(data.get("audit_log_path"), var_root / "audit" / "audit.jsonl"),
            memory_db_path=resolve(data.get("memory_db_path"), var_root / "memory" / "memory.sqlite3"),
            default_skill_timeout_s=int(data.get("default_skill_timeout_s", 60)),
            app_root=resolve(data.get("app_root"), app_root_default),
            skill_root=resolve(data.get("skill_root"), skill_root_default),
            ros_bridge_mode=str(data.get("ros_bridge_mode", "cli")),
            daemon_host=str(os.environ.get("AGENTIC_DAEMON_HOST", data.get("daemon_host", "127.0.0.1"))),
            daemon_port=int(os.environ.get("AGENTIC_DAEMON_PORT", data.get("daemon_port", 8765))),
            session_root=resolve(os.environ.get("AGENTIC_SESSION_ROOT", data.get("session_root")), var_root / "sessions"),
            storage_root=resolve(os.environ.get("AGENTIC_STORAGE_ROOT", data.get("storage_root")), var_root / "storage"),
            context_root=resolve(os.environ.get("AGENTIC_CONTEXT_ROOT", data.get("context_root")), var_root / "context"),
            scheduler_policy=str(data.get("scheduler_policy", "single_robot_fifo")),
            memory_provider=str(data.get("memory_provider", "sqlite")),
            tool_root=resolve(data.get("tool_root"), agentic_home / "tools"),
            bridge_root=resolve(data.get("bridge_root"), agentic_home / "bridges" / "ros2"),
            bridge_profile_root=resolve(data.get("bridge_profile_root"), etc_root / "bridge_profiles"),
            enable_daemon_api=bool(data.get("enable_daemon_api", True)),
            kernel=dict(kernel_data or {}),
        )


def load_places(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    path = _first_existing(
        [
            root / "configs" / "places.yaml",
            Path(os.environ.get("AGENTIC_ETC", "/opt/agentic/etc")) / "places.yaml",
        ]
    )
    return load_yaml(path).get("places", {}) if path else {}


def load_safety(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    path = _first_existing(
        [
            root / "configs" / "safety.yaml",
            Path(os.environ.get("AGENTIC_ETC", "/opt/agentic/etc")) / "safety.yaml",
        ]
    )
    return load_yaml(path).get("safety", {}) if path else {}


def _config_base(path: Path | None, repo_root: Path, agentic_home: Path) -> Path:
    if path and _is_relative_to(path.resolve(), (agentic_home / "etc").resolve()):
        return agentic_home
    return repo_root


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _first_existing(paths: list[Path | None]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path if path.is_absolute() else (find_repo_root() / path)
    return None
