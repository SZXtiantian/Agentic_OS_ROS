# model_library

Source: `agentic_runtime_src/agentic_os/kernel/model_library`

`model_library` is the contract for edge, side, and optional model management.

## App-Facing Entry

There is no stable direct App API yet.

## Status

This module is reserved for model routing and model asset management. App-facing model query, model selection, and local model invocation APIs will be expanded later.

## Notes

Current apps should use models through `ctx.llm.*` or explicit perception/system skills instead of depending on `model_library` internals.
