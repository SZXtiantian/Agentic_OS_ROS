# Robot Photographer Agent

AIOS-compatible and AgenticOS-safe real robot photography Agent App.

Read-only photo with required real LLM planning:

```bash
AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 \
  /opt/agentic/bin/agentic --real --json --require-llm "拍一张工作区照片"
```

Named arm motion is disabled unless explicitly allowed:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
  /opt/agentic/bin/agentic --real --allow-arm-motion --yes "把相机抬起来再拍一张"
```

The app uses plan-first execution. It never imports ROS2 libraries and never touches camera or servo topics directly.

LLM boundary:

- AgenticOS Runtime owns `LLMChat` and the provider client.
- This Agent App consumes the injected `llm_chat` interface only.
- Required-LLM acceptance fails if Dispatcher or App planning falls back to `rule_based`.
- LLM output is only a bounded JSON photo plan; deterministic execution and all hardware access still go through AgenticOS capabilities, permissions, locks, safety guards, bridge/HAL, and audit.
