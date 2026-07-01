# ctx.gripper.open

低力打开夹爪。

## Signature

```python
async def open(timeout_s: int = 5) -> SkillResult
```

## Equivalent

```python
await ctx.gripper.set("open", force="low", timeout_s=timeout_s)
```

## Example

```python
await ctx.gripper.open()
```
