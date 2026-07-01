# ctx.robot.stop

`stop`: Ask Runtime to perform a controlled robot stop.

```python
async def stop(reason: str = "app_requested") -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `reason` | `str` | `"app_requested"` | Stop reason recorded with runtime and audit context. |

## Returns

`SkillResult`

## Example

```python
await ctx.robot.stop(reason="operator_requested")
```
