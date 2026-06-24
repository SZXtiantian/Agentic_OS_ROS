#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

from agentic_runtime.config import ROS_BRIDGE_MODES
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.provider_contracts import ROS_BRIDGE_UNSUPPORTED_MODES, TRUTH_STATUS_FIELDS, validate_mode_truth

status = KernelService().status()
providers = dict(status.get("providers") or {})
required = set(TRUTH_STATUS_FIELDS)
expected = {"ros_bridge", "llm", "human", "context", "memory", "storage", "tool", "skill"}
missing_providers = sorted(expected - set(providers))
if missing_providers:
    raise SystemExit(f"CAPABILITY_TRUTH_FAILED missing providers: {', '.join(missing_providers)}")

for name in sorted(expected):
    provider = dict(providers[name])
    missing_fields = sorted(required - set(provider))
    if missing_fields:
        raise SystemExit(f"CAPABILITY_TRUTH_FAILED {name} missing fields: {', '.join(missing_fields)}")
    validate_mode_truth(
        available_modes=provider.get("available_modes", []),
        implemented_modes=provider.get("implemented_modes", []),
        unsupported_modes=provider.get("unsupported_modes", []),
        reserved_modes=provider.get("reserved_modes", []),
    )
    if not isinstance(provider.get("capability_evidence"), dict) or not provider["capability_evidence"]:
        raise SystemExit(f"CAPABILITY_TRUTH_FAILED {name} missing capability_evidence")

ros_bridge = dict(providers["ros_bridge"])
classified_ros_modes = set(ros_bridge.get("implemented_modes", [])) | set(ros_bridge.get("unsupported_modes", [])) | set(
    ros_bridge.get("reserved_modes", [])
)
if set(ROS_BRIDGE_MODES) - classified_ros_modes:
    missing = ", ".join(sorted(set(ROS_BRIDGE_MODES) - classified_ros_modes))
    raise SystemExit(f"CAPABILITY_TRUTH_FAILED ros_bridge unclassified schema modes: {missing}")
if set(ROS_BRIDGE_UNSUPPORTED_MODES) & set(ros_bridge.get("available_modes", [])):
    raise SystemExit("CAPABILITY_TRUTH_FAILED ros_bridge unsupported mode appears available")

print("CAPABILITY_TRUTH_OK providers=ros_bridge,llm,human,context,memory,storage,tool,skill")
PY
