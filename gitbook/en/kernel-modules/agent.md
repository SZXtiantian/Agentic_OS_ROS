# agent

Source: `agentic_runtime_src/agentic_os/kernel/agent`

`agent` contains agent lifecycle, resource table, cleanup, and error models.

## App-Facing Entry

There is no stable direct App API yet. Agent Apps should not import lifecycle, table, or resource internals from this module.

## Status

Runtime uses this module internally for agent/session lifecycle and resource cleanup. App-facing lifecycle query, suspend, resume, and cleanup APIs will be expanded later.

## Notes

- The App entry point remains the `entrypoint` declared in `app.yaml`.
- Apps express success or failure through structured return values.
- Runtime owns session and agent resource cleanup.
