#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "CHECK_NAME=real_human_file_queue"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1"
echo "CONFIG_PATH=${AGENTIC_RUNTIME_CONFIG:-configs/runtime.yaml}"
echo "PROVIDER_STATUS=$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from pathlib import Path
from agentic_runtime.human_channel import FileHumanQueueChannel
status = FileHumanQueueChannel(Path("/tmp/agentic_verify_human_status")).status()
print(f"available_modes={status['available_modes']} error_code={status['error_code']} missing={status['missing']}")
PY
)"

if [ "${AGENTIC_VERIFY_REAL_HUMAN_QUEUE:-0}" != "1" ]; then
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=set AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 and have an operator append a matching queue response"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_human_queue_contract_is_opt_in_and_never_auto_answers
echo "RESULT=PASS"
echo "ERROR_CODE="
echo "NEXT_ACTION="
