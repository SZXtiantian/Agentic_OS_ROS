#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${AGENTIC_VERIFY_REAL_HUMAN_QUEUE:-0}" != "1" ]; then
  echo "UNVERIFIED_REAL_DEPENDENCY: HUMAN missing=AGENTIC_VERIFY_REAL_HUMAN_QUEUE next_action='set AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 and have an operator append a matching queue response'"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_human_queue_contract_is_opt_in_and_never_auto_answers
