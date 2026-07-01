# human

Source: `agentic_runtime_src/agentic_os/kernel/human`

`human` 管理 operator prompt、确认和人工输入。真实高风险任务应通过 human confirmation 阻断自动执行。

## App 可用入口

高层 SDK：

```python
answer = await ctx.human.ask("确认执行抓取？")
```

System skill：

```python
await ctx.kernel.skill.call(
    "human.ask",
    {
        "question": "Confirm real manipulation",
        "options": ["CONFIRM", "CANCEL"],
        "require_confirmation": True,
    },
)
```

## 开发者注意

- 涉及机械臂、夹爪、导航、抓取和放置时，应在 safety policy 中声明需要确认。
- 没有确认时返回结构化错误，不要继续执行。
- 示例 App 使用 `CONFIRM` 作为明确确认词。
