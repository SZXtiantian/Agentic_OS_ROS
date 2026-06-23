#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

missing=()
[ "${AGENTIC_VERIFY_REAL_LLM:-0}" = "1" ] || missing+=("AGENTIC_VERIFY_REAL_LLM")
[ -n "${AGENTIC_REAL_LLM_BASE_URL:-}" ] || missing+=("AGENTIC_REAL_LLM_BASE_URL")
[ -n "${AGENTIC_REAL_LLM_API_KEY:-}" ] || missing+=("AGENTIC_REAL_LLM_API_KEY")
[ -n "${AGENTIC_REAL_LLM_MODEL:-}" ] || missing+=("AGENTIC_REAL_LLM_MODEL")

if [ "${#missing[@]}" -gt 0 ]; then
  joined="$(IFS=,; echo "${missing[*]}")"
  echo "UNVERIFIED_REAL_DEPENDENCY: LLM missing=${joined} next_action='set real OpenAI-compatible endpoint env vars and AGENTIC_VERIFY_REAL_LLM=1'"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" pytest -q tests/test_real_integration_contracts.py::test_real_llm_provider_contract_is_opt_in_and_never_simulated
