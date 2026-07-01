# ctx.robot.inspect_area

检查已注册地点并返回摘要、对象、异常和 evidence 信息。

## Signature

```python
async def inspect_area(place: str, timeout_s: int = 60) -> InspectionResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `place` | `str` | required | 已注册地点名 |
| `timeout_s` | `int` | `60` | 检查超时，范围 `1..120` |

## Returns

`InspectionResult`

```python
success: bool
summary: str
objects: list[str]
anomalies: list[str]
evidence_path: str
evidence: dict
error_code: str
reason: str
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `robot.inspect_area` |
| 权限 | `perception.inspect` |
| 后端 | ROS2 service `/agentic/perception/inspect_area` |
| 资源锁 | `camera` |
| Safety | known place、允许取消、runtime timeout margin `5s` |
| Timeout | `60s` |

## Common Errors

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `INSPECTION_FAILED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `SKILL_TIMEOUT`

## Example

```python
inspection = await ctx.robot.inspect_area("厨房", timeout_s=60)
await ctx.memory.remember("last_inspection", inspection.to_dict())
```
