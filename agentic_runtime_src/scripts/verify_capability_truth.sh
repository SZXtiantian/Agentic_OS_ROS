#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

from agentic_runtime.kernel_service import KernelService
from agentic_runtime.provider_contracts import TRUTH_STATUS_FIELDS, validate_mode_truth

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

print("CAPABILITY_TRUTH_OK providers=ros_bridge,llm,human,context,memory,storage,tool,skill")
PY
