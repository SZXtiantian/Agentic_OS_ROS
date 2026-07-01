# Error Codes

Common structured error codes:

| Scenario | Error Codes |
| --- | --- |
| Permission denied | `PERMISSION_DENIED`, `ACCESS_DENIED` |
| Human/operator intervention required | `ACCESS_INTERVENTION_REQUIRED`, `ACCESS_INTERVENTION_DENIED` |
| Resource locked | `RESOURCE_LOCKED` |
| Invalid input schema | `SCHEMA_INVALID` |
| Missing or forbidden place | `PLACE_NOT_FOUND`, `FORBIDDEN_ZONE` |
| Robot state not ready | `ROBOT_NOT_LOCALIZED`, `ESTOP_PRESSED` |
| Safety rejected | `SAFETY_REJECTED` |
| Timeout | `SKILL_TIMEOUT`, `NAVIGATION_TIMEOUT` |
| Cancellation | `SKILL_CANCELLED`, `SESSION_STOPPED` |
| ROS2 bridge missing | `ROS_BRIDGE_UNAVAILABLE` |
| ROS2 service/action missing | `ROS_SERVICE_UNAVAILABLE`, `ROS_ACTION_UNAVAILABLE` |
| LLM unavailable | `LLMCHAT_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, `LLM_PROVIDER_REQUEST_FAILED`, `LLM_RESPONSE_INVALID` |
| Human provider | `HUMAN_PROVIDER_UNCONFIGURED`, `HUMAN_BACKEND_UNAVAILABLE`, `HUMAN_OPERATOR_TIMEOUT`, `HUMAN_CANCELLED` |
| Real dependency not verified | `UNVERIFIED_REAL_DEPENDENCY` |
| Unexpected failure | `UNEXPECTED_ERROR` |

Recommended app handling:

```python
from agentic_runtime.errors import AgenticRuntimeError


try:
    await ctx.robot.navigate_to("kitchen")
except AgenticRuntimeError as exc:
    return {"success": False, "error_code": exc.code, "reason": exc.message}
```
