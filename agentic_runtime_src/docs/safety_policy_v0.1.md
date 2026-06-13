# Safety Policy v0.1

Every dangerous robot action must pass through Agentic Runtime permission checks, resource locks, safety guards, and audit logs before any ROS2 bridge invokes robot motion.

## Required Checks

- Permission check: the App must hold every permission listed by the Skill Manifest.
- Resource lock: movement uses `base`; inspection uses `camera`; stop is never blocked by normal locks.
- Safety guard: forbidden zone, localization, estop, and duration constraints are checked before motion.
- Audit log: every skill call writes JSONL with status and structured error code.

## MVP Forbidden Zones

The global safety config includes:

- `stairs`
- `elevator`
- `lab_restricted_zone`

The sample place `楼梯` maps to `stairs` and is not allowed.

## Realtime Control Boundary

LLM and Agent code may choose task-level skills only. Realtime closed-loop behavior remains in ROS2 controllers, Nav2, MoveIt, and drivers.
