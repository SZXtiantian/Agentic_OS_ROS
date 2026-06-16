# camera_arm_inspection_agent

Real-robot AgenticOS camera and manipulator demo app.

Read-only observation:

```bash
/opt/agentic/bin/agentic-run camera_arm_inspection_agent --real --place workspace
```

Arm motion is disabled unless explicitly allowed:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 /opt/agentic/bin/agentic-run camera_arm_inspection_agent --real --place workspace
```

The app uses only AgenticOS SDK calls: camera observation, arm state, allowed named arm action, low-force gripper command, memory, reporting, and stop.
