# Storage

AgenticOS kernel source module for storage syscalls and artifact-safe file
operations. This module is ported from AIOS storage concepts and adapted for
the `/opt/agentic/var/storage` runtime state boundary.

Storage v1 supports AIOS-style operations:

- `sto_mount`
- `sto_create_file`
- `sto_create_directory`
- `sto_write`
- `sto_retrieve`
- `sto_rollback`
- `sto_share`

All paths remain inside the configured storage root. System/audit/bridge/ROS
workspace paths are rejected. LSFS is represented by a disabled adapter shell
until a safe sandboxed integration is wired.
