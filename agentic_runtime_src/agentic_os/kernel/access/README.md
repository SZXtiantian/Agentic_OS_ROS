# Access Manager

`AccessManager` is the kernel access-control layer for resources and high-risk operations.
It does not replace the runtime `PermissionManager`.

- `PermissionManager` checks whether an app manifest declared the skill permissions it needs.
- `AccessManager` checks whether the current subject may access a resource in this session.
- `SafetyGuard` checks whether the physical robot state is safe for an action.
- `ResourceManager` and `DeviceArbiter` serialize physical device ownership.

The default intervention provider denies irreversible operations until a UI or operator channel is wired in.
Tests may use `AlwaysAllowTestInterventionProvider` to exercise confirmed high-risk flows.
