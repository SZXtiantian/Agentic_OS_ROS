# App Manifest

每个 Agent App 使用 `app.yaml` 声明身份、入口、权限、capability、安全策略和运行限制。

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

Manifest 不授予直接 ROS2 访问权限。所有 capability 仍需通过 Runtime 执行。
