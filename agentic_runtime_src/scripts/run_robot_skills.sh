#!/usr/bin/env bash
set -euo pipefail

exec "$(dirname "$0")/run_system_skill_nodes.sh" "$@"
