# Runtime Error Model

Runtime uses structured errors instead of silent failures or fabricated success.

```python
{
    "success": False,
    "error_code": "ROS_BRIDGE_UNAVAILABLE",
    "reason": "...",
    "recoverable": True,
    "suggested_recovery": ["retry", "ask_human", "cancel"],
}
```

Apps should catch `AgenticRuntimeError`:

```python
from agentic_runtime.errors import AgenticRuntimeError


try:
    await ctx.robot.navigate_to("kitchen")
except AgenticRuntimeError as exc:
    return {"success": False, "error_code": exc.code, "reason": exc.message}
```

See [Error Codes](../reference/errors.md) for details.
