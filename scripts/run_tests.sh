#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec agentic_runtime_src/scripts/run_tests.sh
