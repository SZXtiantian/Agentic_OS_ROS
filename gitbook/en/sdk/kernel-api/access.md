# ctx.kernel.access

Kernel access API explicitly checks whether an action is allowed on a resource.

## Methods

```python
await ctx.kernel.access.check(
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

await ctx.kernel.access.assert_allowed(...) -> dict
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
