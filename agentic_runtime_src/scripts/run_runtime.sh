#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../agentic_runtime"
python -m agentic_runtime.cli status
