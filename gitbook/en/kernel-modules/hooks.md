# hooks

Source: `agentic_runtime_src/agentic_os/kernel/hooks`

`hooks` provides Runtime-internal events, queues, metrics, and queue stores.

## App-Facing Entry

There is no direct App API yet.

## Status

Runtime, scheduler, managers, and tests use this module. Robot lanes are separated from generic tool lanes, so robot motion cannot bypass the safety chain through generic tools.

## Notes

- Apps should not manipulate kernel queues directly.
- Use `ctx.kernel.context.*`, `ctx.kernel.storage.*`, or `ctx.report.*` for app-level state and reporting.
- App-facing event subscription APIs will be expanded later.
