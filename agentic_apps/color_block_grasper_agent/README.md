# color_block_grasper_agent

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`color_block_grasper_agent` is a native Agentic App. It does not vendor or wrap
the traditional color-block robot package. Its runtime path uses
`AgentContext`, `ctx.llm.chat_json`, and `ctx.kernel.skill.call(...)`.

For a line-by-line explanation of the vision detection and grasp execution
path, see
[`../../agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`](../../agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md).

Natural-language requests such as "把红色颜色块夹到左边托盘" must be planned by
the Runtime-owned LLM facade. The app does not parse colors or tray names from
text itself. The constrained JSON plan must include `target_color`,
`place_target`, `requires_manipulation`, `needs_confirmation: true`, `steps`,
`risk_class`, and `user_summary`. The app validates the plan and policy before
requesting:

- `arm.move_named` with `arm_home`
- `perception.center_color_block`
- `perception.detect_color_block`
- `perception.capture_photo`
- `manipulation.pick_color_block`
- `arm.move_named` with `arm_home` immediately after pick, preserving the
  closed gripper in the bridge
- `perception.verify_held_color_block`
- `manipulation.place_color_block`
- `human.ask`
- `report.say`

The app must not create provider clients, read API keys, or call OpenAI,
LiteLLM, or vLLM SDKs directly. If the LLM facade or provider is unavailable,
the app returns `LLMCHAT_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, or another
stable LLM error and does not continue as a successful path.

The real grasp path first moves the arm to `arm_home`, centers the requested
color block in the camera view with the tuned visual-servo bridge, then runs a
fresh detection so the pick backend receives a current `camera_position_m`.

After `manipulation.pick_color_block`, the app immediately returns the arm to
`arm_home` while the manipulation bridge preserves the closed gripper. It then
captures post-pick evidence, reads arm/gripper state, and calls
`perception.verify_held_color_block` with a post-reset verification context.
`held=true` from the pick backend is only candidate evidence. The final result
is successful only when the independent verifier records `verified_held=true`
from fresh evidence showing the target color in the gripper-held ROI, not
overlapping the pre-pick tabletop detection, and visually larger/closer than
the pre-pick detection. In the post-reset arm-home posture, depth delta is
recorded as evidence but is not a hard pass/fail gate because that geometry
does not preserve the pre-reset depth relationship. The app also repeats held
verification after a short delay so a block that slips back to the tabletop
cannot be reported as success.
The block stays clamped until the later place step releases it.

If the real detector, camera bridge, held verifier, arm bridge, gripper bridge,
or manipulation backend is not configured, the app returns stable errors such
as `UNVERIFIED_REAL_DEPENDENCY`, `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`,
`COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE`, or
`MANIPULATION_BACKEND_UNAVAILABLE`. It never invents a detection, pose,
evidence file, pick result, placement result, or held-object verification.

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
centering, detection, and held verification, the Agentic manipulation bridge to
expose pick and place contracts, and a configured Runtime LLM provider. When
those dependencies are missing, report:

```text
UNVERIFIED_REAL_DEPENDENCY
missing: AGENTIC_LLM_ENABLED=1, AGENTIC_LLM_REQUIRE=1, perception.center_color_block, perception.detect_color_block, perception.verify_held_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the Runtime LLM provider and real Agentic bridge contracts, then rerun real-e2e
```
