# Agentic SDK

Agentic SDK 是 Agent App 代码直接使用的 Python 接口。Runtime 会把 `AgentContext` 注入 App，App 通过 `ctx` 请求受权限、安全检查、资源锁和审计保护的能力。

Agent App 不直接导入 `rclpy`，不发布 `/cmd_vel`，不直接调用 Nav2、MoveIt 或机器人厂商驱动。

## SDK Namespaces

| Namespace | 用途 |
| --- | --- |
| `ctx.robot` | 读取机器人状态、导航、区域检查、停止 |
| `ctx.world` | 把地点名称解析成 Runtime 可用的位置 |
| `ctx.perception` | 观察环境、拍照、获取感知结果 |
| `ctx.arm` | 读取机械臂状态、执行命名动作 |
| `ctx.gripper` | 控制夹爪开合或设置夹爪命令 |
| `ctx.memory` | 保存和读取 App 的小段数据 |
| `ctx.storage` | 查询 App 可用的 evidence 记录；当前公开最近照片记录 |
| `ctx.human` | 向人询问或请求确认 |
| `ctx.report` | 报告任务进度和结果 |
| `ctx.llm` | 请求 Runtime 执行结构化 LLM 调用 |

`ctx.kernel.*` 不放在 Agentic SDK 入门表里。它是 Agentic System Call facade，用于需要直接发起 Kernel system call 的场景。

## Result Behavior

SDK 方法成功时返回 dataclass、普通 Python 值或 `SkillResult`。失败时通常抛出 `AgenticRuntimeError` 或其子类。

`SkillResult` 的基本形状是：

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

## Example

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
