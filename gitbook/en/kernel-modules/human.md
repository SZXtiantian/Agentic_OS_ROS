# human

Source: `agentic_runtime_src/agentic_os/kernel/human`

`human` manages operator prompts, confirmations, and human input. Real high-risk tasks should be blocked on human confirmation.

## App-Facing Entry

High-level SDK:

```python
answer = await ctx.human.ask("Confirm grasp execution?")
```

System skill:

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

## Notes

- Arm, gripper, navigation, pick, and place actions should declare confirmation in safety policy.
- Without confirmation, return a structured error and stop.
- The example app uses `CONFIRM` as the explicit confirmation word.
