# scheduler

Source: `agentic_runtime_src/agentic_os/kernel/scheduler`

`scheduler` manages Runtime-internal syscalls, task graphs, lanes, resource leases, preemption, and audit lifecycle.

## App-Facing Entry

There is no direct App API yet.

## Status

Apps start requests through SDK/skill calls, and Runtime passes those requests to the scheduler. App-facing scheduling status, task graph diagnostics, and cancellation APIs will be expanded later.

## Notes

- Apps should not construct scheduler TaskNodes to call ROS2, Nav2, or MoveIt.
- Robot motion uses a dedicated lane and is non-preemptible by default.
- To cancel work, use Runtime-exposed cancel/status facades rather than internal scheduler queues.
