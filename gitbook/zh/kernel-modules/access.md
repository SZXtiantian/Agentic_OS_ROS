# access

Source: `agentic_runtime_src/agentic_os/kernel/access`

`access` 负责 session 内资源访问和高风险操作确认。它不替代 app manifest permission；permission 判断 App 是否声明了能力，access 判断当前 subject 在当前 session 是否可以访问某个资源或执行某个高风险动作。

## App 可用入口

```python
await ctx.kernel.access.check(...)
await ctx.kernel.access.assert_allowed(...)
```

高风险 system skill 也会在 Runtime 内自动经过 access/intervention，例如 `robot.navigate_to`、`arm.move_named`、`manipulation.pick_color_block`。

## 返回

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

## 开发者注意

- App 不能用 access 结果绕过 permission、resource lock 或 safety guard。
- 不可逆操作可能需要 operator/UI intervention。
- 测试可以使用 allow provider，但真实路径不能默认放行高风险动作。
