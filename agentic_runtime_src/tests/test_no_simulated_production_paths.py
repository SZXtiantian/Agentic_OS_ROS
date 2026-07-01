from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client.client import create_ros_bridge_client
from agentic_runtime.server import RuntimeServer


PRODUCTION_ROOTS = (
    Path("agentic_runtime"),
    Path("agentic_os"),
    Path("configs"),
)

DISALLOWED_PRODUCTION_PATTERNS = {
    "simulated backend class": re.compile(r"class\s+\w*(?:Mock|Fake|Stub|Dummy)\w*(?:Provider|Backend|Client|Bridge|Manager)\b"),
    "simulated backend symbol": re.compile(r"\b(?:Mock|Fake|Stub|Dummy)\w*(?:Provider|Backend|Client|Bridge|Manager)\b"),
    "simulated backend config": re.compile(r"\b(?:backend|type)\s*[:=]\s*['\"]?(?:mock|fake|stub|dummy)['\"]?", re.IGNORECASE),
    "simulated skill provider transport": re.compile(r"\bskill_provider_transport\s*:\s*mock\b", re.IGNORECASE),
    "mock backend toggle": re.compile(r"\ballow_mock_backends\b"),
    "mock perception evidence": re.compile(r"\bperception_backend_status\b.*\bMOCK\b"),
    "simulated success text": re.compile(r"\b(?:mock|fake|stub|dummy)[_\s-]*(?:success|camera|bridge|provider|backend)\b", re.IGNORECASE),
}

ALLOWLISTED_PRODUCTION_FILES = {
    Path("agentic_runtime/simulation.py"),
}


def _production_files(runtime_src: Path) -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        base = runtime_src / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix in {".py", ".yaml", ".yml"}:
                files.append(path)
    return sorted(files)


def test_ros_bridge_factory_has_no_mock_client_import(runtime_src):
    source = (runtime_src / "agentic_runtime" / "ros_bridge_client" / "client.py").read_text(encoding="utf-8")

    assert "MockRosBridgeClient" not in source
    assert "mock_client" not in source
    assert not (runtime_src / "agentic_runtime" / "ros_bridge_client" / "mock_client.py").exists()


def test_production_sources_have_no_simulated_backend_success_paths(runtime_src):
    failures: list[str] = []
    for path in _production_files(runtime_src):
        rel = path.relative_to(runtime_src)
        if rel in ALLOWLISTED_PRODUCTION_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        for label, pattern in DISALLOWED_PRODUCTION_PATTERNS.items():
            match = pattern.search(source)
            if match:
                failures.append(f"{rel}: {label}: {match.group(0)!r}")

    assert failures == []


def test_runtime_server_create_has_no_simulated_mode_parameter():
    with pytest.raises(TypeError):
        RuntimeServer.create(mock=True)
    with pytest.raises(TypeError):
        RuntimeServer.create(mock=True, bridge_client=object())


def test_ros_bridge_factory_has_no_simulated_mode_parameter_and_config_rejects_it(tmp_path):
    config = RuntimeConfig.load()
    with pytest.raises(TypeError):
        create_ros_bridge_client(config, mock=True)

    config_path = tmp_path / "runtime.yaml"
    config_path.write_text("runtime:\n  skill_provider_transport: mock\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CONFIG_VALUE_UNSUPPORTED"):
        RuntimeConfig.load(config_path)
