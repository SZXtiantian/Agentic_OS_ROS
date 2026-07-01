# device_arbitration

Source: `agentic_runtime_src/agentic_os/kernel/device_arbitration`

`device_arbitration` handles physical device ownership and resource arbitration for resources such as base, camera, arm, and gripper.

## App-Facing Entry

There is no direct App API yet.

## Status

Apps trigger arbitration indirectly through `resource_requirements.locks` in system skill contracts. App-facing device occupancy, wait queue, and diagnostic APIs will be expanded later.

## Notes

- Declare required devices in `resources` inside `app.yaml`.
- Declare resource locks in skill contracts.
- Do not implement ad hoc device locks inside an Agent App.
