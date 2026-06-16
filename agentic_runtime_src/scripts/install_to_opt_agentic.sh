#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/opt/agentic"
INSTALL_USER="${SUDO_USER:-$(id -un)}"
INSTALL_GROUP="$(id -gn "$INSTALL_USER" 2>/dev/null || id -gn)"

if sudo -n true >/dev/null 2>&1; then
  sudo mkdir -p "$TARGET"
  sudo chown -R "$INSTALL_USER:$INSTALL_GROUP" "$TARGET"
else
  TARGET="/home/ubuntu/staging_opt_agentic"
  mkdir -p "$TARGET"
fi

mkdir -p \
  "$TARGET/bin" \
  "$TARGET/etc" \
  "$TARGET/etc/secrets" \
  "$TARGET/etc/bridge_profiles" \
  "$TARGET/lib/python3" \
  "$TARGET/sdk/python" \
  "$TARGET/sdk/cpp" \
  "$TARGET/agentic_os" \
  "$TARGET/agentic_os/hardware" \
  "$TARGET/bridges/ros2" \
  "$TARGET/skills" \
  "$TARGET/var/log" \
  "$TARGET/var/audit" \
  "$TARGET/var/evidence" \
  "$TARGET/var/memory" \
  "$TARGET/var/world_model" \
  "$TARGET/var/storage" \
  "$TARGET/var/context" \
  "$TARGET/var/sessions" \
  "$TARGET/var/tasks" \
  "$TARGET/var/tasks/plans" \
  "$TARGET/docs" \
  "$TARGET/tests"

rmdir "$TARGET/hardware" 2>/dev/null || true

RSYNC_EXCLUDES=(
  --exclude '__pycache__/'
  --exclude '.pytest_cache/'
)

rsync -a --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC_ROOT/docs/" "$TARGET/docs/"
rsync -a --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC_ROOT/tests/" "$TARGET/tests/"
rsync -a --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC_ROOT/skills/" "$TARGET/skills/"
rsync -a --delete --delete-excluded \
  "${RSYNC_EXCLUDES[@]}" \
  --exclude 'agentic_os/' \
  "$SRC_ROOT/agentic_runtime/" "$TARGET/lib/python3/agentic_runtime/"
rsync -a --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" "$SRC_ROOT/agentic_os/" "$TARGET/agentic_os/"
mkdir -p "$TARGET/agentic_os/hardware"

cp "$SRC_ROOT/configs/agentic.yaml" "$TARGET/etc/agentic.yaml"
rm -f "$TARGET/etc/agentic_sim.yaml"
if [ -f "$SRC_ROOT/configs/agentic_robot.yaml" ]; then
  cp "$SRC_ROOT/configs/agentic_robot.yaml" "$TARGET/etc/agentic_robot.yaml"
fi
cp "$SRC_ROOT/configs/permissions.yaml" "$TARGET/etc/permissions.yaml"
cp "$SRC_ROOT/configs/safety.yaml" "$TARGET/etc/safety.yaml"
cp "$SRC_ROOT/configs/models.yaml" "$TARGET/etc/models.yaml"
cp "$SRC_ROOT/configs/capabilities.yaml" "$TARGET/etc/capabilities.yaml"
cp "$SRC_ROOT/configs/places.yaml" "$TARGET/etc/places.yaml"
if [ -d "$SRC_ROOT/configs/bridge_profiles" ]; then
  rsync -a --delete --delete-excluded "${RSYNC_EXCLUDES[@]}" \
    "$SRC_ROOT/configs/bridge_profiles/" "$TARGET/etc/bridge_profiles/"
fi

cat > "$TARGET/README.md" <<'EOF'
# AgenticOS System Root

`/opt/agentic` is the installed AgenticOS root.

Top-level ownership:

- `bin/`: command wrappers only.
- `lib/python3/agentic_runtime/`: executable Python runtime.
- `agentic_os/`: AgenticOS kernel source, ABI maps, and architecture taxonomy.
- `etc/`: configuration, bridge profiles, and local secrets.
- `skills/`: installed skill and capability manifests.
- `bridges/`: AgenticOS-owned hardware or middleware adapters.
- `sdk/`: exported SDK artifacts.
- `tests/`: installed conformance tests.
- `docs/`: human-readable documentation.
- `var/`: mutable runtime state.

Kernel modules in `agentic_os/kernel` are importable OS modules ported from
AIOS concepts. Runtime service code in `lib/python3/agentic_runtime` may adapt
them, but ROS2-specific imports belong only in bridge packages under
`/home/ubuntu/agentic_ws/ros2_bridge_src`.
EOF

cat > "$TARGET/pytest.ini" <<'EOF'
[pytest]
testpaths = tests
pythonpath = lib/python3
addopts = -p no:cacheprovider
EOF

cat > "$TARGET/setup.bash" <<'EOF'
#!/usr/bin/env bash

export AGENTIC_HOME=/opt/agentic
export AGENTIC_ETC=$AGENTIC_HOME/etc
export AGENTIC_VAR=$AGENTIC_HOME/var
export AGENTIC_SKILLS=$AGENTIC_HOME/skills
export AGENTIC_DOCS=$AGENTIC_HOME/docs

export PATH=$AGENTIC_HOME/bin:$PATH
export PYTHONPATH=$AGENTIC_HOME/lib/python3:$AGENTIC_HOME:$PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1

if [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  source /opt/ros/humble/setup.bash
  set -u
fi
if [ -f /home/ubuntu/ros2_ws/install/setup.bash ]; then
  set +u
  source /home/ubuntu/ros2_ws/install/setup.bash
  set -u
fi
if [ -f /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash ]; then
  set +u
  source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash
  set -u
fi

if [ "${AGENTIC_QUIET:-0}" != "1" ]; then
  echo "Agentic OS environment loaded from $AGENTIC_HOME"
fi
EOF

if [ "$TARGET" != "/opt/agentic" ]; then
  sed -i "s#/opt/agentic#$TARGET#g" "$TARGET/setup.bash"
fi
chmod +x "$TARGET/setup.bash"

cat > "$TARGET/bin/agenticctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_QUIET=1 source "${AGENTIC_HOME:-/opt/agentic}/setup.bash"
if [ "$#" -eq 0 ]; then
  set -- status
fi
python -m agentic_runtime.cli "$@"
EOF

cat > "$TARGET/bin/agentic-run" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_QUIET=1 source "${AGENTIC_HOME:-/opt/agentic}/setup.bash"
python -m agentic_runtime.cli run-app "$@"
EOF

cat > "$TARGET/bin/agentic-app" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_QUIET=1 source "${AGENTIC_HOME:-/opt/agentic}/setup.bash"
python -m agentic_runtime.cli "$@"
EOF

cat > "$TARGET/bin/agentic" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_QUIET=1 source "${AGENTIC_HOME:-/opt/agentic}/setup.bash"
if [ "${1:-}" = "enter" ] || [ "${1:-}" = "env" ]; then
  shift || true
  export PS1="(agentic) ${PS1:-\\u@\\h:\\w\\$ }"
  echo "AgenticOS environment active. Try: agentic chat --real"
  exec "${SHELL:-/bin/bash}" -i "$@"
fi
if [ "${1:-}" = "chat" ] || [ "${1:-}" = "shell" ]; then
  shift || true
  python -m agentic_runtime.nl_gateway "$@"
  exit $?
fi
if [ "${1:-}" = "photo" ]; then
  shift || true
  python -m agentic_runtime.photo_cli "$@"
  exit $?
fi
if [ "${1:-}" = "run" ] || [ "${1:-}" = "run-app" ] || [ "${1:-}" = "status" ] || [ "${1:-}" = "sessions" ] || [ "${1:-}" = "session" ] || [ "${1:-}" = "stop" ] || [ "${1:-}" = "audit" ] || [ "${1:-}" = "apps" ] || [ "${1:-}" = "skills" ] || [ "${1:-}" = "refresh" ] || [ "${1:-}" = "bridge" ] || [ "${1:-}" = "tasks" ] || [ "${1:-}" = "task" ]; then
  python -m agentic_runtime.cli "$@"
  exit $?
fi
python -m agentic_runtime.nl_gateway "$@"
EOF

cat > "$TARGET/bin/agenticd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_QUIET=1 source "${AGENTIC_HOME:-/opt/agentic}/setup.bash"
python -m agentic_runtime.kernel_service.server "$@"
EOF

chmod +x "$TARGET/bin/agentic" "$TARGET/bin/agenticctl" "$TARGET/bin/agentic-run" "$TARGET/bin/agentic-app" "$TARGET/bin/agenticd"

find "$TARGET" -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf {} +

if [ "$TARGET" = "/opt/agentic" ]; then
  sudo chown -R "$INSTALL_USER:$INSTALL_GROUP" "$TARGET/var" "$TARGET/etc/secrets"
  sudo chmod -R u+rwX,g+rwX "$TARGET/var"
fi

echo "Agentic OS installed to $TARGET"
