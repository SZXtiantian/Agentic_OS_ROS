# Robot Photographer Agent

AIOS-compatible and AgenticOS-safe real robot photography Agent App.

Read-only photo:

```bash
agentic photo --real "拍一张照片"
```

Named arm motion is disabled unless explicitly allowed:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 agentic photo --real --allow-arm-motion --yes "把相机抬起来再拍一张"
```

The app uses plan-first execution. It never imports ROS2 libraries and never touches camera or servo topics directly.
