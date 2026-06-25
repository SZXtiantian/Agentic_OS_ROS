# Agentic App Developer Guide

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

An Agentic App is task orchestration code that runs above Agentic Runtime. It
uses `AgentContext` to request high-level, permissioned, audited capabilities.
It is not a ROS2 package, not a bridge node, and not a hardware driver.

## Start From The Template

Use one of these commands:

```bash
cp -R agentic_apps/app_template agentic_apps/my_agent
```

```bash
python scripts/create_agentic_app.py my_agent
```

The scaffold writes `.agentic_template_source` with:

```text
source=agentic_apps/app_template
template_name=app_template
```

Every native app keeps:

```text
README.md
app.yaml
main.py
prompts/system.md
storage/.gitkeep
tests/
workflows/default.yaml
```

## app.yaml

`app.yaml` declares the app identity, entrypoint, permissions, required
capabilities, safety policy, and runtime limits. The entrypoint stays:

```yaml
entrypoint: main:run
```

`permissions` are the app's grant set. `required_capabilities` are the
capabilities the app expects Runtime and Kernel to expose. Dangerous robot
actions still pass through Runtime permission checks, resource locks, safety
guards, and audit logs.

## main.py

The entrypoint is:

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs):
    ...
```

Use `ctx.kernel.context`, `ctx.kernel.memory`, `ctx.kernel.storage`,
`ctx.kernel.tool`, `ctx.kernel.skill`, or the high-level SDK namespaces such as
`ctx.robot`, `ctx.perception`, `ctx.arm`, `ctx.gripper`, `ctx.human`, and
`ctx.report`.

Agent Apps must not import ROS2 client libraries, MoveIt, Nav2, bridge source,
message packages, or hardware SDKs. They must not publish or subscribe to robot
topics, call Nav2 or MoveIt actions, shell out to `ros2`, or implement realtime
closed-loop control. Bridge/HAL code belongs under `ros2_bridge_src`.

## System LLM Planning

Apps that perform natural-language understanding or task planning must call the
Agentic OS system LLM interface. The preferred SDK path is:

```python
result = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
)
```

`ctx.llm.chat_json` delegates to `RuntimeServer.llm_chat` through the runtime
injected into `AgentContext`. Provider clients, model config, secrets, retries,
and provider-specific parsing remain owned by Runtime/Kernel. Agent Apps must
not construct OpenAI-compatible clients, import LiteLLM/vLLM/OpenAI SDKs, read
API keys, or treat structured keyword parameters as natural-language
understanding.

The LLM output must be a constrained JSON plan. The app owns deterministic
schema validation, policy validation, permission/resource checks, safety
guards, real capability execution, audit evidence, memory/storage writes, and
reporting. If `ctx.llm` returns `LLMCHAT_UNAVAILABLE`,
`LLM_PROVIDER_UNCONFIGURED`, or another LLM error, the app must return a stable
failure. It must not continue as a successful rule planner path.

Tutorial acceptance for `hello_world_agent` and `color_block_grasper_agent`
runs with `AGENTIC_LLM_REQUIRE=1` or an equivalent `--require-llm` command.

## Real-Only Behavior

Apps must not create surface success when a real backend is missing. Missing
providers return stable errors such as `SKILL_BACKEND_UNAVAILABLE`,
`ROS_BRIDGE_UNAVAILABLE`, `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`,
`MANIPULATION_BACKEND_UNAVAILABLE`, or `UNVERIFIED_REAL_DEPENDENCY`.

Bare kernel smoke exercises Kernel managers without a `RuntimeServer`. Real
runtime smoke starts `RuntimeServer`, loads the skill registry, and uses real
runtime backends such as the file report sink.

## Storage, Prompts, Workflows, Tests

`storage/` is app-owned durable output space. Do not commit generated runs,
audit logs, task logs, real photos, videos, secrets, or `/opt/agentic/var`.

`prompts/` stores system prompts for app-owned planning instructions. Apps
still use Runtime-owned LLM services and must not read model secrets.

`workflows/default.yaml` records the default workflow shape. `tests/` verifies
manifest shape, boundary rules, real-only failures, and smoke behavior.

## Commands

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
scripts/verify_agentic_app_tutorials.sh
```

For Runtime-level tests:

```bash
PYTHONPATH=. pytest -q
scripts/run_tests.sh
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
```

Audit and task status are exposed through Runtime session records, syscall
metadata, and JSONL audit logs. Keep those generated files out of git.

## Tutorials

- `agentic_runtime_src/docs/tutorials/hello_world_agent.md`
- `agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`

The Hello World tutorial shows Runtime LLM JSON planning followed by context,
memory, storage, tool, skill, and report calls. The color-block tutorial shows
Runtime LLM JSON planning followed by deterministic validation and real
perception/manipulation contracts without copying a traditional robot app.
