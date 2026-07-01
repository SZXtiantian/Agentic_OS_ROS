# llm_core

Source: `agentic_runtime_src/agentic_os/kernel/llm_core`

`llm_core` is the ROS-free LLM syscall and provider adapter layer. It handles provider metadata, routing, active call status, cancellation, and normalized errors.

## App-Facing Entry

For ordinary JSON planning:

```python
result = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    timeout_s=30,
)
```

Advanced syscall facade:

```python
await ctx.kernel.llm.chat(messages, timeout_s=30)
await ctx.kernel.llm.complete(prompt, timeout_s=30)
await ctx.kernel.llm.embed(texts, timeout_s=30)
await ctx.kernel.llm.status(call_id="")
await ctx.kernel.llm.cancel(call_id="")
```

## Notes

- LLMs may plan, explain, summarize, or perform non-realtime reasoning.
- LLMs must not directly run realtime robot control loops.
- The example app requires the LLM to return a JSON plan and then validates it deterministically.
- Missing provider configuration, missing optional dependencies, and remote provider failures should return structured errors.
