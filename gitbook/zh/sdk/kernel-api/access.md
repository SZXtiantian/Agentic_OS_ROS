# ctx.kernel.access

`ctx.kernel.access` 是 access manager facade，用于显式检查某个 action 对某个 resource 是否允许。

它不生成 queued Agentic System Call，也没有 `operation_type`。返回值是 access decision dict，而不是 `KernelSDKResult`。

## ctx.kernel.access.check

`check`: 返回 access decision。

```python
async def check(
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    owner_agent: str = "",
    owner_user: str = "",
    labels: Iterable[str] = (),
    groups: Iterable[str] = (),
    irreversible: bool = False,
    reason: str = "",
) -> dict
```

## ctx.kernel.access.assert_allowed

`assert_allowed`: 调用 `check`，如果不允许则抛出 `KernelAccessDeniedError`。

```python
async def assert_allowed(*args, **kwargs) -> dict
```

## Returns

```python
{
    "allowed": bool,
    "error_code": str,
    "reason": str,
    "requires_intervention": bool,
    "intervention_id": str,
    "metadata": dict,
}
```

## Example

```python
decision = await ctx.kernel.access.check(
    action="execute",
    resource_type="robot_motion",
    resource_id="robot.navigate_to",
    irreversible=True,
    reason="navigate to kitchen",
)
```
