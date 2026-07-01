# Color Block Grasper Agentic App

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`color_block_grasper_agent` is a native Agentic App. It is not a ROS2 package
and does not wrap the traditional color-block robot package. Existing robot
code may be used only as a legacy reference for task flow and bridge contract
design; it must not be copied, imported, packaged, or called by this app.

## Create

```bash
python scripts/create_agentic_app.py color_block_grasper_agent \
  --description "Template-derived Agentic App that orchestrates real color block detection, pick, and place capabilities through Agentic OS."
```

The app keeps the template core files and `.agentic_template_source`.

## Manifest

`app.yaml` declares `llm.external.call`, robot state, perception, arm, gripper,
manipulation, human, memory, storage, and report permissions. Required
capabilities include:

- `agenticos.runtime.llm_chat`
- `llm.chat`
- `arm.get_state`
- `arm.move_named`
- `perception.center_color_block`
- `perception.detect_color_block`
- `perception.verify_held_color_block`
- `manipulation.pick_color_block`
- `manipulation.place_color_block`
- `perception.capture_photo`
- `human.ask`
- `report.say`

Manipulation is enabled only through Runtime permission checks, resource locks,
safety guards, and audit logs.

## State Machine

`main.py` follows this order:

1. Read natural language from `message` or `task_text`.
2. Call `ctx.llm.chat_json(...)`, which delegates to Runtime-owned
   `RuntimeServer.llm_chat`.
3. Validate the constrained JSON plan. Required fields are `target_color`,
   `place_target`, `requires_manipulation`, `needs_confirmation: true`,
   `steps`,
   `risk_class`, and `user_summary`.
4. Validate deterministic policy and required app permissions.
5. Write task context and start storage evidence.
6. Ask for human confirmation when the LLM plan requires it.
7. Check `robot.get_state` and `arm.get_state`; arm state also carries gripper
   readiness.
8. Call `arm.move_named` with `arm_home` to start from the calibrated grasp
   posture.
9. Call `perception.center_color_block` so the tuned visual-servo bridge aligns
   the requested color block in the camera view.
10. Call `perception.detect_color_block` after centering.
11. Call `perception.capture_photo` for pre-pick evidence.
12. Call `manipulation.pick_color_block`.
13. Call `arm.move_named` with `arm_home`; the manipulation bridge preserves the
    closed gripper when the previous gripper command was close.
14. Capture post-pick evidence and call `perception.verify_held_color_block`
    with a post-reset verification context.
15. Continue only if the verification result contains `verified_held=true`.
16. Call `manipulation.place_color_block` or keep the gripper in
    `hold_position`.
17. Write memory and storage result evidence.
18. Call `report.say`.

Allowed plan colors are `red`, `green`, `blue`, and `yellow`. A plan with any
other color returns `COLOR_BLOCK_LLM_PLAN_INVALID`. The app must not parse the
color or destination from natural-language text with string matching or regular
expressions.

If the Runtime LLM facade or provider is unavailable, the app returns a stable
LLM error such as `LLMCHAT_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, or
`COLOR_BLOCK_LLM_PLAN_REQUIRED`. It must not continue as a successful path.

## Skill Contracts

The runtime skill manifests are:

- `agentic_runtime_src/system_skills/perception.detect_color_block/SKILL.md`
- `agentic_runtime_src/system_skills/perception.center_color_block/SKILL.md`
- `agentic_runtime_src/system_skills/perception.verify_held_color_block/SKILL.md`
- `agentic_runtime_src/system_skills/arm.get_state/SKILL.md`
- `agentic_runtime_src/system_skills/arm.move_named/SKILL.md`
- `agentic_runtime_src/system_skills/manipulation.pick_color_block/SKILL.md`
- `agentic_runtime_src/system_skills/manipulation.place_color_block/SKILL.md`

They map to Agentic bridge contracts:

- `/agentic/perception/detect_color_block`
- `/agentic/perception/center_color_block`
- `/agentic/perception/verify_held_color_block`
- `/agentic/arm/get_state`
- `/agentic/arm/move_named`
- `/agentic/manipulation/pick_color_block`
- `/agentic/manipulation/place_color_block`

These contracts require real bridge implementations. If the detector, camera,
arm, gripper, held-block verifier, or manipulation backend is missing, the app
returns stable errors such as `UNVERIFIED_REAL_DEPENDENCY`,
`COLOR_BLOCK_CAPABILITY_UNAVAILABLE`, `COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE`,
or `MANIPULATION_BACKEND_UNAVAILABLE`. It must not invent coordinates, images,
pick results, placement results, or held-object verification.

`manipulation.pick_color_block` returning `success=true` or `held=true` is not a
completion criterion. A real tutorial acceptance must include post-pick image
and metadata evidence plus `perception.verify_held_color_block` output proving
the requested color block is in the gripper-held ROI, no longer overlaps the
pre-pick tabletop detection, and appears larger/closer to the gripper camera
than the pre-pick detection under the current verification posture. If the red
block merely disappears from the tabletop, is pushed into the ROI while still
table-bound, or the verifier cannot
prove it is held, the app must return `COLOR_BLOCK_PICK_VERIFICATION_FAILED`.
In the post-reset `arm_home` posture, depth delta is retained as evidence but
is not the hard acceptance gate; ROI position, size ratio, non-overlap, and
closed-gripper state carry the held check.
The app repeats held verification after a short delay; a block that is lifted
briefly but slips back to the tabletop is not a successful tutorial result.

## Legacy Boundary

Traditional robot code can explain business flow: detect target color, confirm,
pick, place, and handle failure. It cannot become the Agentic App runtime path.
The native app may only call Agentic SDK and kernel skill contracts.

The native app also may only consume the system LLM facade. It must not create
provider clients, read API keys, or call OpenAI/LiteLLM/vLLM SDKs directly.

## Tests

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
scripts/verify_agentic_app_tutorials.sh
```

The tutorial verification script exports `AGENTIC_LLM_REQUIRE=1`, so acceptance
cannot pass by skipping LLM planning.

## Real-E2E

Run real color-block acceptance only on a prepared robot workspace with an
operator present:

```bash
AGENTIC_VERIFY_REAL_COLOR_BLOCK_GRASPER=1 \
AGENTIC_VERIFY_REAL_ROS2=1 \
AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION=1 \
AGENTIC_LLM_ENABLED=1 \
AGENTIC_LLM_REQUIRE=1 \
PYTHONPATH=agentic_runtime_src \
pytest -q agentic_apps/color_block_grasper_agent/tests
```

If those dependencies are not configured, report:

```text
UNVERIFIED_REAL_DEPENDENCY
missing: AGENTIC_LLM_ENABLED=1, AGENTIC_LLM_REQUIRE=1, perception.center_color_block, perception.detect_color_block, perception.verify_held_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the Runtime LLM provider and Agentic perception/manipulation/held-verification bridge contracts, then rerun real-e2e
```

Evidence is recorded in app result storage, memory records, syscall metadata,
and audit logs. Do not commit generated evidence, storage runs, task logs, audit
logs, real photos, or secrets.
