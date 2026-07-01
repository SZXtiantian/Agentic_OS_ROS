# access

Source: `agentic_runtime_src/agentic_os/kernel/access`

`access` handles session-scoped resource access and high-risk operation approval. It does not replace app manifest permissions. Permissions decide whether an app declared a capability; access decides whether the current subject may use a resource or perform a high-risk action in the current session.

## App-Facing Entry

```python
await ctx.kernel.access.check(...)
await ctx.kernel.access.assert_allowed(...)
```

High-risk system skills also pass through access/intervention inside Runtime, such as `robot.navigate_to`, `arm.move_named`, and `manipulation.pick_color_block`.

## Return Shape

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

## Notes

- Apps cannot use access results to bypass permissions, resource locks, or safety guards.
- Irreversible operations may require operator/UI intervention.
- Tests may use an allow provider, but real paths must not default-allow high-risk actions.
