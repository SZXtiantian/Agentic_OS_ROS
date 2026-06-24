#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

missing=()
[ "${AGENTIC_VERIFY_REAL_LLM:-0}" = "1" ] || missing+=("AGENTIC_VERIFY_REAL_LLM")
[ -n "${AGENTIC_REAL_LLM_BASE_URL:-}" ] || missing+=("AGENTIC_REAL_LLM_BASE_URL")
[ -n "${AGENTIC_REAL_LLM_API_KEY:-}" ] || missing+=("AGENTIC_REAL_LLM_API_KEY")
[ -n "${AGENTIC_REAL_LLM_MODEL:-}" ] || missing+=("AGENTIC_REAL_LLM_MODEL")

echo "CHECK_NAME=real_llm_provider"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_LLM=1,AGENTIC_REAL_LLM_BASE_URL,AGENTIC_REAL_LLM_API_KEY,AGENTIC_REAL_LLM_MODEL"
echo "CONFIG_PATH=${AGENTIC_MODELS_CONFIG:-configs/models.yaml}"
echo "PROVIDER_STATUS=$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from agentic_runtime.kernel_service import KernelService
status = KernelService().status()["providers"]["llm"]
print(f"available_modes={status['available_modes']} error_code={status['error_code']} missing={status['missing']}")
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
