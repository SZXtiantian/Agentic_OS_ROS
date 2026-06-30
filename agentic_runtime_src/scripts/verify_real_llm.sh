#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${AGENTIC_VERIFY_REAL_LLM:-0}" = "1" ]; then
  eval "$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import os
import shlex

from agentic_runtime.llm.config import load_llm_config

missing = [
    name
    for name in ("AGENTIC_REAL_LLM_BASE_URL", "AGENTIC_REAL_LLM_API_KEY", "AGENTIC_REAL_LLM_MODEL")
    if not os.environ.get(name)
]
if missing:
    try:
        cfg = load_llm_config().require_ready()
    except Exception:
        raise SystemExit(0)
    values = {
        "AGENTIC_REAL_LLM_BASE_URL": cfg.base_url,
        "AGENTIC_REAL_LLM_API_KEY": cfg.api_key,
        "AGENTIC_REAL_LLM_MODEL": cfg.model,
    }
    for name in missing:
        if values.get(name):
            print(f"export {name}={shlex.quote(str(values[name]))}")
PY
)"
fi

missing=()
[ "${AGENTIC_VERIFY_REAL_LLM:-0}" = "1" ] || missing+=("AGENTIC_VERIFY_REAL_LLM")
[ -n "${AGENTIC_REAL_LLM_BASE_URL:-}" ] || missing+=("AGENTIC_REAL_LLM_BASE_URL")
[ -n "${AGENTIC_REAL_LLM_API_KEY:-}" ] || missing+=("AGENTIC_REAL_LLM_API_KEY")
[ -n "${AGENTIC_REAL_LLM_MODEL:-}" ] || missing+=("AGENTIC_REAL_LLM_MODEL")

echo "CHECK_NAME=real_llm_provider"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_LLM=1,AGENTIC_REAL_LLM_BASE_URL,AGENTIC_REAL_LLM_API_KEY,AGENTIC_REAL_LLM_MODEL"
echo "CONFIG_PATH=${AGENTIC_MODELS_CONFIG:-configs/models.yaml}"
echo "PROVIDER_STATUS=$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from agentic_runtime.llm.config import load_llm_config

try:
    cfg = load_llm_config().require_ready()
except Exception as exc:
    print(f"state=unavailable error_code={getattr(exc, 'code', type(exc).__name__)}")
else:
    print(
        "state=configured "
        f"provider={cfg.provider} "
        f"base_url_present={bool(cfg.base_url)} "
        f"model_present={bool(cfg.model)} "
        f"api_key_present={bool(cfg.api_key)}"
    )
PY
)"

if [ "${#missing[@]}" -gt 0 ]; then
  joined="$(IFS=,; echo "${missing[*]}")"
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=set real OpenAI-compatible endpoint env vars and AGENTIC_VERIFY_REAL_LLM=1; missing=${joined}"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_llm_provider_contract_is_opt_in_and_never_simulated
echo "RESULT=PASS"
echo "ERROR_CODE="
echo "NEXT_ACTION="
