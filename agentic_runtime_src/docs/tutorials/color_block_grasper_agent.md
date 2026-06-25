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
- `perception.detect_color_block`
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
8. Call `perception.detect_color_block`.
9. Call `perception.capture_photo`.
10. Call `manipulation.pick_color_block`.
11. Call `manipulation.place_color_block`.
12. Write memory and storage result evidence.
13. Call `report.say`.

Allowed plan colors are `red`, `green`, `blue`, and `yellow`. A plan with any
other color returns `COLOR_BLOCK_LLM_PLAN_INVALID`. The app must not parse the
color or destination from natural-language text with string matching or regular
expressions.

If the Runtime LLM facade or provider is unavailable, the app returns a stable
LLM error such as `LLMCHAT_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, or
`COLOR_BLOCK_LLM_PLAN_REQUIRED`. It must not continue as a successful path.

## Skill Contracts

The runtime skill manifests are:

- `agentic_runtime_src/skills/perception_detect_color_block.yaml`
- `agentic_runtime_src/skills/manipulation_pick_color_block.yaml`
- `agentic_runtime_src/skills/manipulation_place_color_block.yaml`

They map to Agentic bridge contracts:

- `/agentic/perception/detect_color_block`
- `/agentic/manipulation/pick_color_block`
- `/agentic/manipulation/place_color_block`

These contracts require real bridge implementations. If the detector, camera,
arm, gripper, or manipulation backend is missing, the app returns stable errors
such as `UNVERIFIED_REAL_DEPENDENCY`, `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`, or
`MANIPULATION_BACKEND_UNAVAILABLE`. It must not invent coordinates, images,
pick results, or placement results.

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
missing: AGENTIC_LLM_ENABLED=1, AGENTIC_LLM_REQUIRE=1, perception.detect_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the Runtime LLM provider and Agentic perception/manipulation bridge contracts, then rerun real-e2e
```

Evidence is recorded in app result storage, memory records, syscall metadata,
and audit logs. Do not commit generated evidence, storage runs, task logs, audit
logs, real photos, or secrets.
