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

`app.yaml` declares robot state, perception, arm, gripper, manipulation, human,
memory, storage, and report permissions. Required capabilities include:

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

1. Normalize `color`, `place_target`, `require_confirmation`, `evidence_label`,
   and `timeout_s`.
2. Write task context and start storage evidence.
3. Check `robot.get_state` and `arm.get_state`; arm state also carries gripper
   readiness.
4. Ask for human confirmation when required.
5. Call `perception.detect_color_block`.
6. Call `perception.capture_photo`.
7. Call `manipulation.pick_color_block`.
8. Call `manipulation.place_color_block`.
9. Write memory and storage result evidence.
10. Call `report.say`.

Allowed colors are `red`, `green`, `blue`, and `yellow`. Unsupported colors
return `COLOR_BLOCK_COLOR_NOT_ALLOWED`.

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

## Tests

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
scripts/verify_agentic_app_tutorials.sh
```

## Real-E2E

Run real color-block acceptance only on a prepared robot workspace with an
operator present:

```bash
AGENTIC_VERIFY_REAL_COLOR_BLOCK_GRASPER=1 \
AGENTIC_VERIFY_REAL_ROS2=1 \
AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION=1 \
PYTHONPATH=agentic_runtime_src \
pytest -q agentic_apps/color_block_grasper_agent/tests
```

If those dependencies are not configured, report:

```text
UNVERIFIED_REAL_DEPENDENCY
missing: perception.detect_color_block, manipulation.pick_color_block, manipulation.place_color_block
next_action: configure the Agentic perception and manipulation bridge contracts, then rerun real-e2e
```

Evidence is recorded in app result storage, memory records, syscall metadata,
and audit logs. Do not commit generated evidence, storage runs, task logs, audit
logs, real photos, or secrets.
