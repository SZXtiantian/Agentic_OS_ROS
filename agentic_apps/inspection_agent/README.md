# inspection_agent

Foundation-complete Agent App for inspecting a named room through Agentic OS high-level APIs.

Run:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli run-app inspection_agent --place 厨房
```

This is a real-runtime smoke command. If ROS2 bridge services are unavailable, the runtime returns stable bridge/backend error codes instead of simulating success.

The app resolves a place, checks robot state, navigates through `ctx.robot.navigate_to`, inspects the area, stores `last_inspection`, and reports the result.
