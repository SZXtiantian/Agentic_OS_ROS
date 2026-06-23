#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${PYTHONPATH:-.}"

git diff --check
python scripts/check_forbidden_imports.py
python scripts/check_filesystem_layout.py
scripts/verify_capability_truth.sh
scripts/verify_no_mvp_language.sh
pytest -q

echo "FOUNDATION_VERIFY_OK"
