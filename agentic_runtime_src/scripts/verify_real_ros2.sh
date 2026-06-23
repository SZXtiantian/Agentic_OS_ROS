#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${AGENTIC_VERIFY_REAL_ROS2:-0}" != "1" ]; then
  echo "UNVERIFIED_REAL_DEPENDENCY: ROS2 missing=AGENTIC_VERIFY_REAL_ROS2 next_action='set AGENTIC_VERIFY_REAL_ROS2=1 on a host with ros2 CLI and AgenticOS bridge services'"
  exit 2
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "UNVERIFIED_REAL_DEPENDENCY: ROS2 missing=ros2 next_action='source ROS2 setup and install ros2 CLI'"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_ros2_bridge_contract_is_opt_in_and_never_simulated
