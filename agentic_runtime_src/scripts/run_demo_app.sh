#!/usr/bin/env bash
set -euo pipefail

MESSAGE="${1:-app template smoke}"
RUNTIME_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RUNTIME_SRC"
python -m agentic_runtime.cli run-app app_template --message "$MESSAGE" --real
