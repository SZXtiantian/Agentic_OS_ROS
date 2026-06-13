# room_inspection_app

MVP Agent App for inspecting a named room through Agentic OS high-level APIs.

Run:

```bash
cd agentic_runtime
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
```

The app resolves a place, checks robot state, navigates through `ctx.robot.navigate_to`, inspects the area, stores `last_inspection`, and reports the result.
