# Quickstart

This flow shows a minimal Agent App requesting high-level robot capabilities through the SDK.

## 1. Create an app

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
```

## 2. Write the entrypoint

`agentic_apps/my_agent/main.py`

```python
from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "kitchen") -> dict:
    try:
        resolved = await ctx.world.resolve_place(place)
        await ctx.robot.navigate_to(resolved.name, timeout_s=120)
        inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)
        await ctx.memory.remember("last_inspection", inspection.to_dict())
        await ctx.report.say(f"{resolved.name} inspection completed.")
        return {"success": True, "inspection": inspection.to_dict()}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

## 3. Declare permissions

`app.yaml`

```yaml
entrypoint: main:run
permissions:
  - robot.move
  - robot.stop
  - world.read
  - perception.inspect
  - memory.write
  - report.say
required_capabilities:
  - robot.navigate_to
  - robot.inspect_area
  - world.resolve_place
  - memory.remember
  - report.say
```

## 4. Test boundaries

```bash
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

Agent Apps must not directly access ROS2, Nav2, MoveIt, or low-level robot topics.
