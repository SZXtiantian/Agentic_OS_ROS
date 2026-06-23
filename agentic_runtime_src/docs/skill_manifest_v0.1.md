# Skill Manifest v0.1

Skill manifests live under `agentic_runtime/skills/*.yaml`.

Skill manifests will declare high-level robot capabilities, required permissions, resource locks, safety policy references, and audit behavior.

## Required Fields

```yaml
name: string
version: string
description: string

input_schema:
  type: object
  required: []
  properties: {}

output_schema:
  type: object
  required: []
  properties: {}

permission_requirements: string[]

resource_requirements:
  locks: string[]

safety_constraints:
  require_known_place: bool
  require_localized: bool
  require_estop_released: bool
  forbidden_zone_check: bool
  allow_cancel: bool
  max_duration_s: int

timeout_s: int

retry_policy:
  max_attempts: int
  retry_on: string[]

backend:
  type: ros2_action | ros2_service | ros2_topic | runtime_internal
  bridge: string
  ros2_action_name: string
  ros2_action_type: string

observability:
  audit: bool
  record_feedback: bool
  record_result: bool
```

## Foundation Skills

- `robot.get_state`
- `world.resolve_place`
- `robot.navigate_to`
- `robot.inspect_area`
- `robot.stop`
- `memory.remember`
- `memory.recall`
- `human.ask`
- `report.say`

Every skill call writes an audit record, including permission failures, safety rejections, resource lock failures, timeouts, cancellations, and backend failures.
