# AgenticOS Filesystem Layout

This document defines the intended `/opt/agentic` filesystem contract. It exists
to prevent architecture metadata, executable runtime code, app workspace code,
ROS2 bridge code, and mutable state from being mixed together.

## Core Rule

`/opt/agentic` is the installed AgenticOS system root.

Inside it, every top-level directory must have exactly one ownership meaning:

```text
/opt/agentic
  README.md      root ownership map
  setup.bash     environment loader
  pytest.ini     installed conformance test config
  bin/          operator commands and thin CLI wrappers
  lib/          importable executable runtime libraries
  agentic_os/   AgenticOS kernel source, ABI maps, architecture module taxonomy
  etc/          system configuration and local secrets
  system_skills/ system SKILL.md capability contracts
  bridges/      installed hardware or middleware adapter ownership
  sdk/          exported SDK artifacts for external developers
  tests/        installed conformance tests
  docs/         human-readable documentation
  var/          mutable runtime state
```

No directory should be both a conceptual OS map and an executable Python package.

Generated cache directories such as `__pycache__` and `.pytest_cache` are not
part of the installed filesystem contract.

## Source And Publish Trees

The active development source trees on this host are intentionally outside
`/opt/agentic`:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src
/home/ubuntu/agentic_ws/src/<agent_app>
/home/ubuntu/agentic_ws/ros2_bridge_src/<bridge_package>
```

These source trees are installed into `/opt/agentic` by the installer; the whole
source workspace must not be copied into `/opt/agentic` as a git repository.

Legacy or handoff repositories such as:

```text
/home/ubuntu/Agentic_OS_ROS_publish
```

are publication/export mirrors, not active runtime roots. If such a repository
is kept, it should either be updated from the active `agentic_ws` sources before
publishing, or archived outside the active deployment path. It must not be
treated as `/opt/agentic`, and it must not be used as a second source of truth
for runtime, app, or bridge behavior.

## Authoritative Meanings

### `/opt/agentic/bin`

Contains command entrypoints only.

Allowed:

```text
agentic
agenticctl
agentic-run
agentic-app
future: agenticd
```

These files should be thin wrappers around installed runtime modules. Business
logic does not belong here.

### `/opt/agentic/lib/python3/agentic_runtime`

Contains executable Python daemon/service wrapper implementation.

Allowed:

```text
kernel service / daemon API code
session manager and CLI/server lifecycle
permission manager
safety/resource/audit orchestration
kernel-backed memory/storage/tool/context/config adapters
SDK runtime implementation
mock and non-rclpy bridge clients
```

Not allowed:

```text
rclpy imports
ROS2 message/action imports
architecture-only skeleton trees
duplicated /opt/agentic/agentic_os content
parallel source-of-truth implementations of kernel modules
docs copied as Python package data unless explicitly needed at runtime
__pycache__ or pytest cache directories
```

This means `agentic_runtime/agentic_os` should be removed from the runtime
package in the cleanup phase. It is currently a duplicate of `/opt/agentic/agentic_os`
and should not be treated as runtime implementation.

Runtime manager modules should wrap or adapt `agentic_os.kernel` modules rather
than reimplementing syscall, scheduler, memory, storage, context, tool,
world-model, or device-arbitration semantics in parallel.

### `/opt/agentic/agentic_os`

Contains AgenticOS kernel source, architecture contracts, ABI maps, and module
taxonomy. This tree is importable as the `agentic_os` Python package after
`/opt/agentic/setup.bash` is sourced.

Allowed:

```text
ROS2-safe kernel module code ported from AIOS concepts
kernel module maps
system call ABI descriptions
security layer descriptions
hardware adapter contracts
SDK contract descriptions
README/spec/manifest-style files
```

Not allowed:

```text
duplicated agentic_runtime service implementation
runtime state
ROS2 bridge source packages
App source code
duplicated lib/python3 runtime code
rclpy imports
```

This directory is comparable to the OS kernel/source and ABI layer. The runtime
service implementation still lives in `/opt/agentic/lib/python3/agentic_runtime`,
but `agentic_os/kernel` must not be empty documentation-only scaffolding.

Canonical kernel source modules:

```text
system_call
capability
skill_library
memory
model_library
context
tool
storage
scheduler
perception
device_arbitration
world_model
```

Legacy names such as `memory_mngt`, `context_mngt`, `tool_mngt`,
`agent_scheduler`, `agent_friendly_perception`, and `side_model_library` should
not reappear.

### `/opt/agentic/etc`

Contains system configuration.

Allowed:

```text
agentic.yaml
permissions.yaml
safety.yaml
places.yaml
capabilities.yaml
models.yaml
robot_profiles/
secrets/
```

Rules:

- `secrets/` is local-machine only.
- Do not copy secrets into docs, manifests, audit logs, or source code.
- `robot_profiles/` describes concrete robot/middleware adapter mappings.

### `/opt/agentic/system_skills`

Contains installed system skill contracts.

These are the capability-level ABI visible to Agent Apps through the SDK. They
are `SKILL.md` files with `agentic-skill` metadata, not Python runtime code.

### `/opt/agentic/bridges`

Contains AgenticOS-owned hardware / middleware adapter ownership.

For ROS2:

```text
/opt/agentic/bridges/ros2
  bridge lifecycle metadata
  generated adapter config
  installed bridge artifact metadata
  future installer output
```

ROS2 source packages may live under:

```text
/home/ubuntu/agentic_ws/ros2_bridge_src
```

That path is only the current ROS2/colcon source and build workspace. It is not
an Agent App workspace. The bridge still belongs to AgenticOS as its HAL/driver
layer.

### `/opt/agentic/sdk`

Contains exported SDK artifacts for app developers.

Examples:

```text
sdk/python
sdk/cpp
```

The current Python SDK implementation may live inside
`/opt/agentic/lib/python3/agentic_runtime/sdk` because it is part of the runtime
package. `/opt/agentic/sdk/python` should be treated as an exported developer
artifact location, not a second implementation copy.

### `/opt/agentic/docs`

Contains human-readable documentation.

Docs may reference runtime modules, OS contracts, apps, and bridges, but docs
are not the source of executable runtime behavior.

### `/opt/agentic/tests`

Contains installed conformance tests for the AgenticOS runtime and filesystem
contract.

These tests are not runtime implementation. They may be removed from a minimal
production image, but if present they must not create persistent cache files in
the installed tree.

### `/opt/agentic/var`

Contains mutable runtime state.

Allowed:

```text
audit/
log/
memory/
sessions/
storage/
world_model/
context/
```

No source code, manifests, or static architecture docs should be written here.

## Historical Violations The Guard Prevents

The filesystem guard should fail if any of these issues reappear:

1. `/opt/agentic/agentic_os` and
   `/opt/agentic/lib/python3/agentic_runtime/agentic_os` are duplicated.
2. The install script copies any architecture skeleton into
   `/opt/agentic/lib/python3/agentic_runtime`.
3. `/opt/agentic/hardware` exists next to `/opt/agentic/agentic_os/hardware` or
   `/opt/agentic/bridges/ros2`, which creates three possible hardware meanings.
4. `__pycache__` or `.pytest_cache` exists in the installed system root.
5. Contract module directories use inconsistent legacy abbreviations such as
   `memory_mngt`, `agent_scheduler`, or `side_model_library`.

## Cleanup Decision

The cleanup phase should do this in order:

1. Move source-side architecture skeletons out of
   `agentic_runtime/agentic_os` into a non-runtime source location such as
   `agentic_os/` or `share/agentic_os/`.
2. Update `install_to_opt_agentic.sh` so it does not copy
   `agentic_runtime/agentic_os` into `/opt/agentic/lib/python3/agentic_runtime`.
3. Keep `/opt/agentic/agentic_os` as the AgenticOS kernel source, ABI, and
   architecture taxonomy tree.
4. Keep `/opt/agentic/lib/python3/agentic_runtime` as executable Python runtime
   implementation only.
5. Deprecate `/opt/agentic/hardware` unless a distinct role is defined. Prefer:
   `/opt/agentic/agentic_os/hardware` for contracts and
   `/opt/agentic/bridges/<type>` for concrete adapters.
6. Add a static filesystem guard that fails if `agentic_runtime/agentic_os`
   reappears under `/opt/agentic/lib/python3`.
7. Keep installed cache directories out of the clean system root.

No runtime behavior should change until this layout contract is accepted.
