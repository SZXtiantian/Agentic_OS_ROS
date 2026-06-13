#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/opt/agentic"

if sudo -n true >/dev/null 2>&1; then
  sudo mkdir -p "$TARGET"
  sudo chown -R "$(id -un):$(id -gn)" "$TARGET"
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
  "$TARGET/var/memory" \
  "$TARGET/var/world_model" \
  "$TARGET/var/storage" \
  "$TARGET/var/context" \
  "$TARGET/var/sessions" \
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

echo "Agentic OS environment loaded from $AGENTIC_HOME"
EOF

if [ "$TARGET" != "/opt/agentic" ]; then
  sed -i "s#/opt/agentic#$TARGET#g" "$TARGET/setup.bash"
fi
chmod +x "$TARGET/setup.bash"

cat > "$TARGET/bin/agenticctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "${AGENTIC_HOME:-/opt/agentic}/setup.bash" >/dev/null
if [ "$#" -eq 0 ]; then
  set -- status
fi
python -m agentic_runtime.cli "$@"
EOF

cat > "$TARGET/bin/agentic-run" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "${AGENTIC_HOME:-/opt/agentic}/setup.bash" >/dev/null
python -m agentic_runtime.cli run-app "$@"
EOF

cat > "$TARGET/bin/agentic-app" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "${AGENTIC_HOME:-/opt/agentic}/setup.bash" >/dev/null
python -m agentic_runtime.cli "$@"
EOF

cat > "$TARGET/bin/agentic" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "${AGENTIC_HOME:-/opt/agentic}/setup.bash" >/dev/null
python -m agentic_runtime.cli "$@"
EOF

cat > "$TARGET/bin/agenticd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source "${AGENTIC_HOME:-/opt/agentic}/setup.bash" >/dev/null
python -m agentic_runtime.kernel_service.server "$@"
EOF

chmod +x "$TARGET/bin/agentic" "$TARGET/bin/agenticctl" "$TARGET/bin/agentic-run" "$TARGET/bin/agentic-app" "$TARGET/bin/agenticd"

find "$TARGET" -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf {} +

echo "Agentic OS installed to $TARGET"
