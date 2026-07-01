# App Manifest

Each Agent App uses `app.yaml` to declare identity, entrypoint, permissions, capabilities, safety policy, and runtime limits.

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
  - memory.write
  - report.say
required_capabilities:
  - robot.get_state
  - robot.navigate_to
  - robot.inspect_area
  - robot.stop
  - world.resolve_place
  - memory.remember
  - report.say
safety_policy:
  allow_autonomous_navigation: true
  allow_manipulation: false
runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 1
```

The manifest never grants direct ROS2 access. Capabilities still execute through Runtime.
