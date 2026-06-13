#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1

python scripts/check_forbidden_imports.py
python scripts/check_filesystem_layout.py

test -f AGENTS.md
test -f docs/architecture.md
test -f configs/places.yaml
test -d agentic_runtime

pytest -q

echo "Agentic OS MVP checks passed."
