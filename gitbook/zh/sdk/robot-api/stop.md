# ctx.robot.stop

`stop`: 请求 Runtime 对机器人执行受控停止。

```python
async def stop(reason: str = "app_requested") -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `reason` | `str` | `"app_requested"` | 停止原因，会进入运行记录和审计上下文。 |

## Returns

`SkillResult`

## Example

```python
await ctx.robot.stop(reason="operator_requested")
```
