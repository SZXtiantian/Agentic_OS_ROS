# Runtime 错误模型

Runtime 使用结构化错误，而不是静默失败或伪造成功。

```python
{
    "success": False,
    "error_code": "ROS_BRIDGE_UNAVAILABLE",
    "reason": "...",
    "recoverable": True,
    "suggested_recovery": ["retry", "ask_human", "cancel"],
}
```

应用应捕获 `AgenticRuntimeError`：

```python
from agentic_runtime.errors import AgenticRuntimeError


try:
    await ctx.robot.navigate_to("厨房")
except AgenticRuntimeError as exc:
    return {"success": False, "error_code": exc.code, "reason": exc.message}
```

详细错误码见 [错误码](../reference/errors.md)。
