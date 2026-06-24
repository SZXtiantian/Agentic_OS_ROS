# color_block_grasper_agent

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`color_block_grasper_agent` is a native Agentic App. It does not vendor or wrap
the traditional color-block robot package. Its runtime path uses
`AgentContext` and `ctx.kernel.skill.call(...)` to request:

- `perception.detect_color_block`
- `perception.capture_photo`
- `manipulation.pick_color_block`
- `manipulation.place_color_block`
- `human.ask`
- `report.say`

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

## Real Integration

A real run requires the Agentic perception bridge to expose color-block
detection and the Agentic manipulation bridge to expose pick and place
contracts. When those dependencies are missing, report:

```text
UNVERIFIED_REAL_DEPENDENCY
missing: perception.detect_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the real Agentic bridge contracts and rerun real-e2e
```
