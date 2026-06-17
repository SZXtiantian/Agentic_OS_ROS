# LLM Core

This package is the ROS-free AgenticOS port of AIOS LLM core semantics.

It provides:

- `LLMConfig` backend metadata
- sequential and smart routing shells
- `LLMAdapter.address_request(syscall)` for scheduler execution
- mock and OpenAI-compatible providers

Default tests use fake or mock providers only. Network-backed providers must be enabled through runtime configuration and are not used by default tests.
