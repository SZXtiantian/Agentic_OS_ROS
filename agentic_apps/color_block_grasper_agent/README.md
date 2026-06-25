# color_block_grasper_agent

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`color_block_grasper_agent` is a native Agentic App. It does not vendor or wrap
the traditional color-block robot package. Its runtime path uses
`AgentContext`, `ctx.llm.chat_json`, and `ctx.kernel.skill.call(...)`.

Natural-language requests such as "把红色颜色块夹到左边托盘" must be planned by
the Runtime-owned LLM facade. The app does not parse colors or tray names from
text itself. The constrained JSON plan must include `target_color`,
`place_target`, `requires_manipulation`, `needs_confirmation: true`, `steps`,
`risk_class`, and `user_summary`. The app validates the plan and policy before
requesting:

- `perception.detect_color_block`
- `perception.capture_photo`
- `manipulation.pick_color_block`
- `manipulation.place_color_block`
- `human.ask`
- `report.say`

The app must not create provider clients, read API keys, or call OpenAI,
LiteLLM, or vLLM SDKs directly. If the LLM facade or provider is unavailable,
the app returns `LLMCHAT_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, or another
stable LLM error and does not continue as a successful path.

If the real detector, camera bridge, arm bridge, gripper bridge, or manipulation
backend is not configured, the app returns stable errors such as
`UNVERIFIED_REAL_DEPENDENCY`, `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`, or
`MANIPULATION_BACKEND_UNAVAILABLE`. It never invents a detection, pose,
evidence file, pick result, or placement result.

## Checks

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

`scripts/verify_agentic_app_tutorials.sh` runs these tutorial checks with
`AGENTIC_LLM_REQUIRE=1`.

## Real Integration

A real run requires the Agentic perception bridge to expose color-block
detection, the Agentic manipulation bridge to expose pick and place contracts,
and a configured Runtime LLM provider. When those dependencies are missing,
report:

```text
UNVERIFIED_REAL_DEPENDENCY
missing: AGENTIC_LLM_ENABLED=1, AGENTIC_LLM_REQUIRE=1, perception.detect_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the Runtime LLM provider and real Agentic bridge contracts, then rerun real-e2e
```
