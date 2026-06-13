# AgenticOS Filesystem Cleanup Plan

This is the immediate Phase -1 plan before AIOS kernel migration.

Do not start the AIOS kernel module migration until this cleanup is complete.

## Objective

Make `/opt/agentic` a clean installed AgenticOS system root with non-overlapping
directory meanings.

The target contract is defined in:

```text
/opt/agentic/docs/filesystem_layout.md
```

## Current Problem

The current tree duplicates architecture metadata inside the executable runtime
package:

```text
/opt/agentic/agentic_os
/opt/agentic/lib/python3/agentic_runtime/agentic_os
```

These trees are almost identical. The runtime package should not contain the
architecture skeleton tree.

Root cause:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

The installer currently copies the full `agentic_runtime/` source tree into
`/opt/agentic/lib/python3/agentic_runtime/`, then copies
`agentic_runtime/agentic_os/` again into `/opt/agentic/agentic_os/`.

## Target Layout

```text
/opt/agentic/bin
  Thin CLI wrappers only.

/opt/agentic/lib/python3/agentic_runtime
  Executable Python runtime implementation only.

/opt/agentic/agentic_os
  OS contracts, ABI maps, module taxonomy, and architecture docs only.

/opt/agentic/bridges
  Installed hardware / middleware adapter ownership.

/opt/agentic/etc
  System config, bridge profiles, and local secrets.

/opt/agentic/skills
  Installed skill / capability manifests.

/opt/agentic/sdk
  Exported SDK artifacts for app developers.

/opt/agentic/docs
  Human-readable documentation.

/opt/agentic/var
  Mutable runtime state only.
```

## Required Changes

1. Move source-side architecture skeletons out of:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/agentic_os
```

into a non-runtime source location, preferably:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_os
```

2. Update:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

so it:

- installs Python runtime from `agentic_runtime/` while excluding `agentic_runtime/agentic_os`;
- installs architecture contracts from source `agentic_os/` into `/opt/agentic/agentic_os`;
- preserves `/opt/agentic/etc/secrets` unless explicitly requested;
- preserves `/opt/agentic/var` runtime state unless explicitly requested;
- creates `/opt/agentic/agentic_os/hardware`, `/opt/agentic/bridges/ros2`, and `/opt/agentic/etc/bridge_profiles`.

3. Remove installed duplicate runtime architecture tree:

```text
/opt/agentic/lib/python3/agentic_runtime/agentic_os
```

only after installer and tests are updated.

4. Decide `/opt/agentic/hardware`:

- preferred: deprecate it if empty;
- keep `/opt/agentic/agentic_os/hardware` for contracts;
- keep `/opt/agentic/bridges/<type>` for concrete adapters.

5. Add a static filesystem guard that fails if the duplicate runtime tree
reappears:

```text
/opt/agentic/lib/python3/agentic_runtime/agentic_os
```

6. Update docs that mention old layout.

## Validation Commands

Run after cleanup:

```bash
/opt/agentic/bin/agenticctl status
/opt/agentic/bin/agentic-run inspection_agent --place 厨房 --mock
```

Run transitional tests if they still live in the source mirror:

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
python scripts/check_forbidden_imports.py
pytest -q
```

Filesystem checks:

```bash
test ! -e /opt/agentic/lib/python3/agentic_runtime/agentic_os
test -d /opt/agentic/agentic_os
test -d /opt/agentic/bridges/ros2
test -d /opt/agentic/etc/bridge_profiles
```

## Done Means

- `/opt/agentic/lib/python3/agentic_runtime` contains only executable runtime code.
- `/opt/agentic/agentic_os` contains importable AgenticOS kernel source,
  ABI maps, and architecture taxonomy.
- The installer no longer recreates the duplicate runtime `agentic_os` tree.
- Secrets and runtime state are not deleted by installer runs.
- Static guard catches layout regression.
- Current mock inspection flow still works.
