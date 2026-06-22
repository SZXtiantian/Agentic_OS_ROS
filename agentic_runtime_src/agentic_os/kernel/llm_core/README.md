# LLM Core

This package is the ROS-free AgenticOS port of AIOS LLM core semantics.

It provides:

- `LLMConfig` backend metadata
- sequential and smart routing shells
- `LLMAdapter.address_request(syscall)` for scheduler execution
- OpenAI-compatible, LiteLLM, HuggingFace, vLLM/OpenAI-compatible, and local provider adapters
- active call status/cancel registry for scheduler-managed syscalls

No simulated provider is available on production paths. Unsupported simulated backend names are reported as unavailable, missing provider configuration is reported as `LLM_PROVIDER_UNCONFIGURED`, missing optional dependencies as `LLM_PROVIDER_DEPENDENCY_MISSING`, and remote provider failures as `LLM_PROVIDER_ERROR`.
