# LLM Provider Testing

AgenticOS uses an OS-owned LLMChat service for natural-language planning.
Agent Apps must not construct provider clients directly, read model configs, or
read API keys. Provider selection, secrets, timeout handling, and JSON parsing
belong to AgenticOS Runtime.

Configured provider:

```text
provider: yunwu
type: openai_compatible_chat
config: /opt/agentic/etc/models.yaml
secret_file: /opt/agentic/etc/secrets/yunwu.env
api_key_env: AGENTIC_LLM_API_KEY or YUNWU_API_KEY
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
sudo install -m 600 /dev/null /opt/agentic/etc/secrets/yunwu.env
# Add AGENTIC_LLM_API_KEY=... locally. Do not commit this file.
```

## Required-LLM Validation

All Robot Photographer acceptance tests must require a real LLM planner. A
test is not accepted if the Dispatcher or App planner falls back to
`planner_mode: rule_based`.

Use:

```bash
AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 \
  /opt/agentic/bin/agentic --real --json --require-llm "拍一张工作区照片"
```

Expected route plan:

```text
route_plan.planner_mode: llm
route_plan.selected_app_id: robot_photographer_agent
route_plan.app_task_input.require_llm: true
```

Expected Robot Photographer photo plan:

```text
app_result.result.planner_mode: llm
app_result.result.intent: capture_photo
app_result.result.risk_class: read_only
```

If LLM output is missing required JSON fields, uses markdown, returns invalid
schema, chooses an unsafe route, or fails network/auth, AgenticOS must return a
structured error such as `DISPATCH_LLM_REQUIRED_FAILED` or
`ROBOT_PHOTOGRAPHER_LLM_REQUIRED_FAILED`. It must not silently use rule-based
planning in required-LLM validation.

## Safety Rules

- Do not store API keys in source, public docs, tests, or app manifests.
- Do not print API keys in logs, audit records, task logs, or test output.
- LLMChat is an AgenticOS Runtime service, not an Agent App implementation
  detail.
- LLM/VLM planning must never perform realtime closed-loop robot control.
- LLM output is only a bounded JSON plan. It must still pass schema validation,
  policy validation, risk classification, confirmation gates, Runtime
  permission checks, resource locks, safety guards, and audit logging.
- `--require-llm` / `AGENTIC_LLM_REQUIRE=1` is mandatory for LLM acceptance
  tests.
