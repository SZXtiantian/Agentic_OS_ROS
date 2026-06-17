# Context Management

Context is split into two responsibilities:

- `ContextManager` / `SessionContextManager` handle robot task session snapshots and recovery metadata.
- `SimpleGenerationContextManager` handles logical LLM generation snapshots such as prompt hash and partial response.

Generation context is only for LLM work. Robot motion is not preempted or resumed through this mechanism.
