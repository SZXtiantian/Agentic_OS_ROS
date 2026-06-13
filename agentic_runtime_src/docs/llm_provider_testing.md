# Optional LLM Provider Testing

AgenticOS does not require an LLM provider for the ROS2 MVP inspection flow.
LLM providers are optional test backends and must not weaken robot safety
boundaries.

Configured optional provider:

```text
provider: yunwu
type: openai_compatible_chat
config: /opt/agentic/etc/models.yaml
api_key_env: YUNWU_API_KEY
recommended_base_url: https://yunwu.ai/v1
```

Base URL candidates:

```text
https://yunwu.ai
https://yunwu.ai/v1
https://yunwu.ai/v1/chat/completions
```

Local secret file:

```bash
source /opt/agentic/etc/secrets/yunwu.env
```

Rules:

- Do not store API keys in public docs or app manifests.
- Do not print API keys in logs, audit records, or test output.
- Do not make `inspection_agent` depend on an external LLM.
- LLM/Agent logic must never perform realtime closed-loop robot control.
