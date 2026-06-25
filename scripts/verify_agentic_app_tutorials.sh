#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export AGENTIC_LLM_REQUIRE=1

python scripts/check_agentic_app_uses_template.py agentic_apps/hello_world_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps

PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/hello_world_agent/tests
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests

for doc in \
  agentic_runtime_src/docs/agentic_app_developer_guide.md \
  agentic_runtime_src/docs/tutorials/hello_world_agent.md \
  agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md
do
  test -f "$doc"
done

echo "AGENTIC_APP_TUTORIALS_OK llm_required=1"
