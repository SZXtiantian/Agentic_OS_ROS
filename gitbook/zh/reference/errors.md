# 错误码

常见结构化错误码：

| 场景 | 错误码 |
| --- | --- |
| 权限不足 | `PERMISSION_DENIED`、`ACCESS_DENIED` |
| 需要人工介入 | `ACCESS_INTERVENTION_REQUIRED`、`ACCESS_INTERVENTION_DENIED` |
| 资源被锁 | `RESOURCE_LOCKED` |
| 输入 schema 错误 | `SCHEMA_INVALID` |
| 地点不存在或禁区 | `PLACE_NOT_FOUND`、`FORBIDDEN_ZONE` |
| 机器人状态不满足 | `ROBOT_NOT_LOCALIZED`、`ESTOP_PRESSED` |
| 安全拒绝 | `SAFETY_REJECTED` |
| 超时 | `SKILL_TIMEOUT`、`NAVIGATION_TIMEOUT` |
| 取消 | `SKILL_CANCELLED`、`SESSION_STOPPED` |
| ROS2 bridge 缺失 | `ROS_BRIDGE_UNAVAILABLE` |
| ROS2 service/action 缺失 | `ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE` |
| LLM 未配置或不可用 | `LLMCHAT_UNAVAILABLE`、`LLM_PROVIDER_UNCONFIGURED`、`LLM_PROVIDER_REQUEST_FAILED`、`LLM_RESPONSE_INVALID` |
| Human provider | `HUMAN_PROVIDER_UNCONFIGURED`、`HUMAN_BACKEND_UNAVAILABLE`、`HUMAN_OPERATOR_TIMEOUT`、`HUMAN_CANCELLED` |
| 真实依赖未验证 | `UNVERIFIED_REAL_DEPENDENCY` |
| 未预期异常 | `UNEXPECTED_ERROR` |

推荐应用侧处理：

```python
from agentic_runtime.errors import AgenticRuntimeError


try:
    await ctx.robot.navigate_to("厨房")
except AgenticRuntimeError as exc:
    return {"success": False, "error_code": exc.code, "reason": exc.message}
```
