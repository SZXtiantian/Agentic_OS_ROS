#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "CHECK_NAME=real_ros2_bridge"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_ROS2=1"
echo "CONFIG_PATH=${AGENTIC_RUNTIME_CONFIG:-configs/runtime.yaml}"
echo "PROVIDER_STATUS=$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from agentic_runtime.provider_contracts import ros_bridge_contract
status = ros_bridge_contract("cli")
print(f"available_modes={status['available_modes']} error_code={status['error_code']} missing={status['missing']}")
PY
)"

if [ "${AGENTIC_VERIFY_REAL_ROS2:-0}" != "1" ]; then
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=set AGENTIC_VERIFY_REAL_ROS2=1 on a host with ros2 CLI and AgenticOS bridge services"
  exit 2
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=source ROS2 setup and install ros2 CLI"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_ros2_bridge_contract_is_opt_in_and_never_simulated
echo "RESULT=PASS"
echo "ERROR_CODE="
echo "NEXT_ACTION="
