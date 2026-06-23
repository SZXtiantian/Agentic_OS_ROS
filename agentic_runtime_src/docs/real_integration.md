# Real Integration Verification

Default tests verify contracts and stable fail-fast behavior. Real dependency
verification is opt-in and must never be replaced by simulated success.

## ROS2

```bash
AGENTIC_VERIFY_REAL_ROS2=1 PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_ros2_bridge_contract_is_opt_in_and_never_simulated
scripts/verify_real_ros2.sh
```

Requires `ros2` CLI and AgenticOS bridge services. Missing dependencies report
`UNVERIFIED_REAL_DEPENDENCY`.

## LLM

```bash
AGENTIC_VERIFY_REAL_LLM=1 \
AGENTIC_REAL_LLM_BASE_URL=https://provider.example/v1 \
AGENTIC_REAL_LLM_API_KEY=... \
AGENTIC_REAL_LLM_MODEL=model-name \
PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_llm_provider_contract_is_opt_in_and_never_simulated
```

Secrets must come from environment variables or a credential helper and must
not be written to code, docs, logs, commits, or snapshots.

## Human Queue

```bash
AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 \
AGENTIC_REAL_HUMAN_QUEUE_ROOT=/opt/agentic/var/human \
PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_human_queue_contract_is_opt_in_and_never_auto_answers
```

An operator must append a matching response. The runtime never auto-fills an
answer.
