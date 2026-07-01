# capability

Source: `agentic_runtime_src/agentic_os/kernel/capability`

`capability` maps stable Agent APIs, manifest declarations, and skill contracts to Runtime/bridge capabilities.

## App-Facing Entry

There is no direct `ctx.kernel.capability.*` App API. Apps use this module indirectly through:

- `permissions` in `app.yaml`
- `required_capabilities` in `app.yaml`
- `agentic_runtime_src/system_skills/*/SKILL.md`
- SDK namespaces such as `ctx.robot.*` and `ctx.perception.*`

## Status

This module currently supports Runtime capability preflight and skill/capability registry behavior. Developer-facing capability query and diagnostic APIs will be expanded later.

## Notes

Declare the capability in the manifest before calling the related SDK method or skill. Do not hard-code ROS2 service/action names in an Agent App.
