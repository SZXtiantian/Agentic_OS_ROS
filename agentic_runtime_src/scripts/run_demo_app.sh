#!/usr/bin/env bash
set -euo pipefail

PLACE="${1:-厨房}"
cd "$(dirname "$0")/../agentic_runtime"
python -m agentic_runtime.cli run-app room_inspection_app --place "$PLACE" --mock
