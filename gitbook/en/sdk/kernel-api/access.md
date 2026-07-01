# ctx.kernel.access

`ctx.kernel.access` is an access manager facade for explicitly checking whether an action is allowed on a resource.

It does not create a queued Agentic System Call and has no `operation_type`. It returns an access decision dict instead of `KernelSDKResult`.

## ctx.kernel.access.check

`check`: Return an access decision.

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

`assert_allowed`: Call `check` and raise `KernelAccessDeniedError` if access is denied.

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
