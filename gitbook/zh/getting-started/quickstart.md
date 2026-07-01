# 快速开始

这个流程展示一个最小 Agent App 如何通过 SDK 请求高层机器人能力。

## 1. 创建应用

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
```

## 2. 编写入口

`agentic_apps/my_agent/main.py`

```python
from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "厨房") -> dict:
    try:
        resolved = await ctx.world.resolve_place(place)
        await ctx.robot.navigate_to(resolved.name, timeout_s=120)
        inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)
        await ctx.memory.remember("last_inspection", inspection.to_dict())
        await ctx.report.say(f"{resolved.name} 检查完成。")
        return {"success": True, "inspection": inspection.to_dict()}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

## 3. 声明权限

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

## 4. 测试边界

```bash
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

Agent App 不允许直接访问 ROS2、Nav2、MoveIt 或底层 robot topic。
