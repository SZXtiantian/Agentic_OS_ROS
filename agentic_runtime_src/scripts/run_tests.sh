#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1

PYTEST_MARK_EXPR="${PYTEST_MARK_EXPR:-not integration and not ros2 and not hardware}"

python scripts/check_forbidden_imports.py
python scripts/check_filesystem_layout.py

test -f AGENTS.md
test -f docs/architecture.md
test -f configs/places.yaml
test -d agentic_runtime

pytest -m "$PYTEST_MARK_EXPR" -q

echo "Agentic OS MVP checks passed."
