# inspection_agent

Primary MVP Agent App for inspecting a named room through Agentic OS high-level APIs.

Run:

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
python -m agentic_runtime.cli run-app inspection_agent --place 厨房 --mock
```

The app resolves a place, checks robot state, navigates through `ctx.robot.navigate_to`, inspects the area, stores `last_inspection`, and reports the result.
