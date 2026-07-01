# Agent App SDK 概览

Agent App SDK 的入口是 Runtime 注入的 `AgentContext`。应用代码不直接访问 ROS2，而是调用高层 namespace：

| Namespace | 用途 |
| --- | --- |
| `ctx.robot` | 机器人状态、导航、区域检查、停止 |
| `ctx.world` | 地点解析和世界模型读取 |
| `ctx.memory` | 应用级键值记忆 |
| `ctx.human` | 向人询问或请求确认 |
| `ctx.report` | 向用户或运行日志报告消息 |
| `ctx.llm` | Runtime-owned JSON planning |
| `ctx.perception` | 观察、拍照和感知 evidence |
| `ctx.arm` | 机械臂状态和命名动作 |
| `ctx.gripper` | 夹爪打开、关闭和低层受控命令 |
| `ctx.storage` | Runtime 管理的照片/evidence 索引 |
| `ctx.kernel` | 进阶 syscall facade |

## 返回模型

底层 skill 返回：

```python
SkillResult(
    success: bool,
    data: dict,
    error_code: str = "",
    reason: str = "",
    recoverable: bool = True,
    suggested_recovery: list[str] = [],
    audit_id: str = "",
)
```

高层 SDK 成功时返回 dataclass 或 `SkillResult`；失败时通常抛出 `AgenticRuntimeError` 或子类。

## 最小示例

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
