# ctx.perception.observe

观察 allowlist 中的目标，例如 workspace。

## Signature

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | 观察目标 |
| `timeout_s` | `int` | `10` | 超时时间，范围 `1..10` |

## Returns

`ObservationResult`

```python
success: bool
summary: str
objects: list[str]
evidence_path: str
evidence: dict
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `perception.observe` |
| 权限 | `perception.observe` |
| 后端 | ROS2 service `/agentic/perception/observe` |
| 资源锁 | `camera` |
| Safety | camera target allowlist |

## Example

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
```
