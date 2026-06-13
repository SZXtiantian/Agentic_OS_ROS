# Agentic OS ROS

This repository contains the current AgenticOS-over-ROS2 MVP source tree for
simulation and real-robot integration on a separate test system.

## Contents

- `agentic_runtime_src/`: AgenticOS runtime, kernel contracts, skill manifests,
  configuration, install scripts, tests, and documentation.
- `agentic_apps/`: Agent Apps, including the current representative
  `inspection_agent`.
- `ros2_bridge_src/`: AgenticOS-owned ROS2 bridge/HAL packages. These are the
  only packages that may import `rclpy`.
- `robot_descriptions/rosorin_description/`: robot description assets copied
  from the current robot workspace for visualization or simulator integration.
- `docs/HANDOFF_SIMULATION_ENV.md`: handoff notes for the next simulation host.

## Architecture Rule

Agent Apps and AgenticOS runtime code must not directly use ROS2 APIs. Robot
movement must flow through:

```text
Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> permission checks / resource locks / safety checks / audit
  -> ROS2 bridge/HAL
  -> ROS2 / Nav2 / robot stack
```

## Current Status

The source was prepared from a real-robot test host. Local fake Nav2/RViz
simulation harnesses were intentionally removed from the runtime workspace.
The next host should add or run its own simulator below the ROS2/Nav2 layer
while keeping AgenticOS APIs and Agent Apps unchanged.

Start with `docs/HANDOFF_SIMULATION_ENV.md`.

