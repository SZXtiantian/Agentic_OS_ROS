from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def find_repo_root(start: Path | None = None) -> Path:
    env_src = os.environ.get("AGENTIC_RUNTIME_SRC")
    if env_src:
        return Path(env_src).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "agentic_runtime").is_dir():
            return candidate
        if (candidate / "configs").is_dir() and (candidate / "AGENTS.md").exists():
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
    allow_mock_backends: bool
    app_root: Path
    skill_root: Path
    ros_bridge_mode: str = "mock"
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

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "RuntimeConfig":
        repo_root = find_repo_root()
        agentic_home = Path(os.environ.get("AGENTIC_HOME", "/opt/agentic")).expanduser()
        if not agentic_home.exists():
            staging = Path("/home/ubuntu/staging_opt_agentic")
            if staging.exists():
                agentic_home = staging

        path = _first_existing(
            [
                Path(config_path).expanduser() if config_path else None,
                Path(os.environ["AGENTIC_RUNTIME_CONFIG"]).expanduser()
                if os.environ.get("AGENTIC_RUNTIME_CONFIG")
                else None,
                agentic_home / "etc" / "agentic.yaml" if os.environ.get("AGENTIC_HOME") else None,
                repo_root / "configs" / "runtime.yaml",
                agentic_home / "etc" / "agentic.yaml",
                Path("/home/ubuntu/configs/runtime.yaml"),
            ]
        )
        data = load_yaml(path).get("runtime", {}) if path else {}

        def resolve(value: str | None, default: Path | str, base: Path = repo_root) -> Path:
            raw = Path(value or default)
            if raw.is_absolute():
                opt_home = Path("/opt/agentic")
                staging = Path("/home/ubuntu/staging_opt_agentic")
                if not opt_home.exists() and staging.exists() and raw == opt_home:
                    return staging
                if not opt_home.exists() and staging.exists() and opt_home in [raw, *raw.parents]:
                    return staging / raw.relative_to(opt_home)
                return raw
            return base / raw

        app_root_default = Path(os.environ.get("AGENTIC_APP_ROOT", repo_root.parent))
        skill_root_default = Path(os.environ.get("AGENTIC_SKILLS", repo_root / "skills"))
        var_root = Path(os.environ.get("AGENTIC_VAR", agentic_home / "var"))
        etc_root = Path(os.environ.get("AGENTIC_ETC", agentic_home / "etc"))

        return cls(
            repo_root=repo_root,
            audit_log_path=resolve(data.get("audit_log_path"), var_root / "audit" / "audit.jsonl"),
            memory_db_path=resolve(data.get("memory_db_path"), var_root / "memory" / "memory.sqlite3"),
            default_skill_timeout_s=int(data.get("default_skill_timeout_s", 60)),
            allow_mock_backends=bool(data.get("allow_mock_backends", True)),
            app_root=resolve(data.get("app_root"), app_root_default),
            skill_root=resolve(data.get("skill_root"), skill_root_default),
            ros_bridge_mode=str(data.get("ros_bridge_mode", "mock")),
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
        )


def load_places(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    path = _first_existing(
        [
            root / "configs" / "places.yaml",
            Path(os.environ.get("AGENTIC_ETC", "/opt/agentic/etc")) / "places.yaml",
            Path("/home/ubuntu/staging_opt_agentic/etc/places.yaml"),
            Path("/home/ubuntu/configs/places.yaml"),
        ]
    )
    return load_yaml(path).get("places", {}) if path else {}


def load_safety(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    path = _first_existing(
        [
            root / "configs" / "safety.yaml",
            Path(os.environ.get("AGENTIC_ETC", "/opt/agentic/etc")) / "safety.yaml",
            Path("/home/ubuntu/staging_opt_agentic/etc/safety.yaml"),
            Path("/home/ubuntu/configs/safety.yaml"),
        ]
    )
    return load_yaml(path).get("safety", {}) if path else {}


def _first_existing(paths: list[Path | None]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path if path.is_absolute() else (find_repo_root() / path)
    return None
