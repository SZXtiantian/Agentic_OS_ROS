# Runtime Overview

Agentic Runtime is the safe execution layer between Agent Apps and ROS2.

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> Agentic OS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

Runtime is responsible for:

- Loading `app.yaml`
- Checking permissions and capabilities
- Running access/intervention checks
- Managing robot resource locks
- Calling safety guards
- Dispatching system skills
- Writing session, syscall, and audit logs

Agent Apps orchestrate task-level capabilities and must not implement realtime control.
