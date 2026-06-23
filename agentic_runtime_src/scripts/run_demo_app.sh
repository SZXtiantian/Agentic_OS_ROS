#!/usr/bin/env bash
set -euo pipefail

PLACE="${1:-厨房}"
RUNTIME_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RUNTIME_SRC"
python -m agentic_runtime.cli run-app room_inspection_app --place "$PLACE" --real
