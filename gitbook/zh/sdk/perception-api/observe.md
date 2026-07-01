# ctx.perception.observe

`observe`: 观察目标区域，并返回摘要、对象和 evidence 信息。

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | 要观察的目标区域。 |
| `timeout_s` | `int` | `10` | 等待观察完成的超时时间。 |

## Returns

`ObservationResult`

```python
ObservationResult(
    success: bool,
    summary: str,
    objects: list,
    evidence_path: str,
    evidence: dict,
)
```

## Example

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
await ctx.report.say(observation.summary)
```
