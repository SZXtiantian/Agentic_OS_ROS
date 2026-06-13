# App Manifest v0.1

The Agent App manifest is stored as `app.yaml` in each app directory.

Manifests will declare app identity, requested permissions, resource needs, and approved high-level capabilities. They must not grant direct ROS2 access to Agent Apps.

## Required Fields

```yaml
name: string
version: string
description: string
entrypoint: string
permissions: string[]
required_capabilities: string[]
safety_policy:
  allow_autonomous_navigation: bool
  allow_manipulation: bool
  require_human_confirmation_for: string[]
  forbidden_zones: string[]
  max_task_duration_s: int
runtime_limits:
  max_concurrent_tasks: int
  max_retries_per_skill: int
  max_memory_write_per_task: int
  llm_planning_enabled: bool
```

## Semantics

- `permissions` are checked against each Skill Manifest before execution.
- `required_capabilities` names must exist in the Skill Registry.
- `safety_policy.forbidden_zones` is merged with global safety configuration.
- `llm_planning_enabled` is `false` for the MVP room inspection app.
- Direct ROS2 access is never granted by an App Manifest.

## Example

```yaml
name: room_inspection_app
version: 0.1.0
description: Inspect a named room using robot navigation and perception.
entrypoint: main:run
permissions:
  - robot.state.read
  - robot.move
  - robot.stop
  - world.read
  - perception.inspect
  - memory.read
  - memory.write
  - human.ask
  - report.say
required_capabilities:
  - robot.get_state
  - robot.navigate_to
  - robot.inspect_area
  - robot.stop
  - world.resolve_place
  - memory.remember
  - memory.recall
  - human.ask
  - report.say
safety_policy:
  allow_autonomous_navigation: true
  allow_manipulation: false
  require_human_confirmation_for:
    - entering_restricted_area
  forbidden_zones:
    - stairs
  max_task_duration_s: 300
runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 1
  max_memory_write_per_task: 20
  llm_planning_enabled: false
```
