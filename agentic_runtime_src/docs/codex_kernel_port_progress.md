# Codex Kernel Port Progress

## Current Status

- Current PR: PR-15 complete.
- Current gate: Final validation complete.
- Next PR: none; PR-00 through PR-15 are complete.

## Changed Files

- `docs/codex_kernel_port_baseline.md`: recorded initial repository, commit, pytest, and forbidden import baseline.
- `docs/codex_kernel_port_progress.md`: created resumable progress log for PR-00 through PR-15.
- `agentic_os/kernel/storage/manager.py`: fixed root path handling so `list('.')` is allowed while read/write/delete root remain forbidden.
- `tests/test_storage_manager.py`: added kernel storage root/path traversal safety tests.
- `scripts/check_forbidden_imports.py`: expanded forbidden ROS direct-access scanning to current `agentic_apps` and stopped skipping storage code.
- `agentic_os/kernel/access/`: added AccessManager, default policy, intervention provider contract, and README.
- `tests/test_access_manager.py`: added owner/shared/admin/audit-delete/robot-motion access tests.
- `agentic_os/kernel/hooks/`: added named kernel queues, global compatibility helpers, metrics snapshot, and README.
- `tests/test_kernel_hooks_queues.py`: added FIFO, timeout, queue snapshot, global reset, and robot/tool lane separation tests.
- `agentic_os/kernel/system_call/models.py`: added event/wait/pid/timing methods while preserving legacy `KernelSyscall.create()` and `to_dict()`.
- `agentic_os/kernel/system_call/schema.py`: added local Query/Response dataclasses.
- `agentic_os/kernel/system_call/{factory,llm,memory,storage,tool,robot,syscall}.py`: added typed syscall family and robot-safe lane routing.
- `agentic_os/kernel/system_call/executor.py`: added queue-backed `execute_request()` while keeping legacy target-handler `execute()`.
- `tests/test_kernel_syscall_async.py`: added event, legacy execution, queue/wait, and timeout tests.
- `tests/test_kernel_syscall_factory.py`: added factory and lane routing tests.
- `agentic_os/kernel/scheduler/{base,fifo_scheduler,rr_scheduler,lanes}.py`: added processing-thread scheduler, lane specs, and RR preemption shell.
- `agentic_os/kernel/scheduler/__init__.py`: exported scheduler v2 while preserving legacy scheduler exports.
- `agentic_os/kernel/scheduler/README.md`: documented legacy/v2 scheduler split and robot motion lane.
- `tests/test_kernel_scheduler_threads.py`: added scheduler lifecycle, success/failure event, status, and custom lane tests.
- `tests/test_kernel_scheduler_robot_lanes.py`: added robot motion serialization and tool/robot lane separation tests.
- `agentic_os/kernel/system_call/protocol.py`: added runtime-checkable `KernelRequestHandler` protocol.
- `agentic_os/kernel/capability/manager.py`: added ROS-free `RobotCapabilityManager` adapter skeleton.
- `agentic_os/kernel/human/`: added ROS-free `HumanInteractionManager` adapter skeleton.
- `tests/test_kernel_manager_contracts.py`: added manager protocol, scheduler protocol, robot no-rclpy, and not-wired tests.
- `agentic_os/kernel/llm_core/`: added LLM config schema, routing, adapter, providers, local backend shell, utilities, errors, and README.
- `tests/test_kernel_llm_core.py`: added routing, fake provider, unsupported provider, tools/JSON passthrough, address_request, and model_library compatibility tests.
- `agentic_os/kernel/context/{session,generation,simple_generation}.py`: added session and generation context managers.
- `agentic_os/kernel/context/__init__.py`: exported session/generation context APIs.
- `tests/test_kernel_generation_context.py`: added session recovery, generation snapshot, prompt hash, and RR non-preempt tests.
- `agentic_os/kernel/memory/`: split memory into note/base/providers/retrievers/injector/extractor/formatter modules and upgraded manager to two-tier memory.
- `tests/test_kernel_memory_manager_v2.py`: added memory note metadata, lexical retrieval, private/shared access, eviction, context injection, and conversation extraction tests.
- `agentic_os/kernel/storage/`: added storage schema, safe/semantic/LSFS filesystem shells, and AIOS-style `sto_*` operations.
- `tests/test_kernel_storage_syscalls.py`: added storage create/write/retrieve/path/overwrite/rollback/share/LSFS tests.
- `agentic_os/kernel/tool/`: added manifest loader, sandbox policy, disabled MCP shell, dynamic ToolManager loading, and expanded robot backdoor deny rules.
- `tests/test_kernel_tool_dynamic_loading.py`: added dynamic load, conflict, robot deny, outside-root, and MCP disabled tests.
- `agentic_runtime/kernel_service/app.py`: replaced the placeholder service with a scheduler-backed KernelService that wires AccessManager, queues, LLM, memory, storage, tool, robot, and human managers.
- `agentic_runtime/server.py`: attaches the KernelService to the runtime executor so SDK contexts can use it.
- `agentic_runtime/sdk/context.py`: exposes a kernel API facade on SDK context while preserving existing robot/memory/human/report APIs.
- `agentic_runtime/sdk/kernel.py`: added SDK wrappers for LLM, memory, storage, and tool kernel requests.
- `agentic_runtime/skill_executor/executor.py`: optionally applies AccessManager checks after manifest permission checks and before resource/safety/audit execution.
- `tests/test_runtime_kernel_service.py`: added KernelService lifecycle, syscall dispatch, SDK facade, and robot skill routing tests.
- `agentic_runtime/hardware_adapter/installer.py`: implemented bridge plan, dry-run install, opt-in real install, command execution capture, and status writing.
- `agentic_runtime/hardware_adapter/bridge_manager.py`: records real profile lifecycle metadata, source commit, ROS distro, endpoint, health command, and install result.
- `agentic_runtime/hardware_adapter/transport.py`: added a concrete ROS-free BridgeTransport facade over the RosBridgeClient protocol.
- `agentic_runtime/hardware_adapter/__init__.py`: exported bridge installer and transport APIs.
- `agentic_runtime/cli.py`: added `agentic-runtime bridge install --dry-run`.
- `tests/test_bridge_manager.py`: added bridge installer, manager metadata, transport contract, and no-runtime-rclpy tests.
- `tests/test_capability_registry.py`: updated robot profile expectation from mock status to real profile lifecycle status.
- `agentic_runtime/sdk/access.py`: added kernel access SDK facade and structured access-denied exception.
- `agentic_runtime/sdk/kernel.py`: exposed `ctx.kernel.access` and kernel status through the SDK compatibility layer.
- `agentic_runtime/sdk/__init__.py`: exported `KernelAccessDeniedError`.
- `tests/test_sdk.py`: added kernel LLM/storage query facade tests, robot SDK routing guard, and access denied error surfacing.
- `agentic_os/kernel/access/policy.py`: expanded robot motion and robot sensor access permissions for runtime skill execution.
- `agentic_runtime/skill_executor/executor.py`: applies AccessManager only to protected robot motion/sensor skill paths and records the existing safety/resource/audit chain.
- `agentic_runtime/server.py`: wires RuntimeServer SkillExecutor to the KernelService AccessManager by default.
- `agentic_runtime/kernel_service/app.py`: records recent kernel syscalls and writes kernel audit records when an AuditLogger is available.
- `tests/test_kernel_e2e_syscall_flow.py`: added LLM -> memory -> storage E2E syscall flow with audit/status assertions.
- `tests/test_kernel_observability.py`: added KernelService status and recent syscall observability tests.
- `tests/test_robot_safety_regression.py`: added generic robot tool bypass, access/safety/resource/audit/bridge, parallel lock, and robot-motion lane serialization regressions.

## Design Decisions

- Use `/home/ubuntu/Agentic_OS_ROS_publish` as the Agentic OS ROS repository.
- Use `/home/ubuntu/AIOS` as the AIOS reference repository.
- Preserve the ROS2 boundary: `agentic_os`, `agentic_runtime`, and `agentic_apps` remain ROS-free.
- Treat existing untracked files under repository `docs/` as user-owned and unrelated to this porting work.
- Storage root is only valid for listing; destructive and write operations must target a non-root relative file path.
- AccessManager is separate from PermissionManager: manifest permission checks stay in runtime, while access checks cover subject/resource/session policy and high-risk intervention.
- Irreversible operations use deny-by-default intervention until an operator UI/provider is wired in.
- Kernel queues are explicit per service/lane stores; global helpers are compatibility shims and can be reset for tests.
- Syscall execution now has two compatible paths: legacy direct handler dispatch and AIOS-style queue-backed request execution.
- Robot capability syscalls route to `robot_motion`, `robot_sensor`, or `human` queues instead of generic tools.
- Scheduler v2 uses background processing threads per lane and calls `manager.address_request(syscall)` for each queued syscall.
- `robot_motion` is non-preemptible and single-worker by default.
- Robot and human managers are scheduler-facing adapter shells; they return structured not-wired errors until runtime provides safe adapters.
- LLM Core uses mock/fake providers in default tests and performs no network access unless a configured provider is explicitly called.
- Optional heavy dependencies remain absent at import time; verified for openai, litellm, transformers, chromadb, mcp, and redis.
- Session/task context is separated from LLM generation context; generation context is logical only and not used to preempt robot motion.
- Memory v1 keeps runtime SQLite compatibility while adding AIOS-like notes, lexical retrieval, optional AccessManager checks, and RAM-to-persistent eviction.
- Storage v1 keeps artifact compatibility while adding safe storage syscall family, version rollback, share intervention, and forbidden system path checks.
- Tool v1 keeps runtime registry compatibility while adding manifest-based local loading and conflict map behavior. MCP remains disabled by default.
- Runtime KernelService is the composition root for AIOS-style kernel managers, queues, scheduler, and syscall execution.
- SDK kernel wrappers call KernelService for non-robot kernel services; robot capabilities remain on the SkillExecutor path with permission/access/resource/safety/audit checks.
- BridgeInstaller is implemented but real command execution is blocked unless `AGENTIC_ALLOW_BRIDGE_INSTALL=1`.
- BridgeManager installs profile metadata by default with a bridge build dry-run; real bridge build execution remains explicit opt-in.
- Runtime-to-bridge access remains ROS-free through `RosBridgeClient` and `BridgeTransport.request(capability, payload)`.
- `ctx.kernel` now exposes LLM, memory, storage, tool, access, and status APIs while robot/arm/gripper/perception SDKs continue to call SkillExecutor.
- Kernel access denial is surfaced as both a structured decision dict and a `KernelAccessDeniedError` with `error_code`.
- RuntimeServer now wires SkillExecutor to KernelService's AccessManager by default, but the executor only applies that gate to protected robot motion and robot sensor skills.
- KernelService observability includes scheduler, queues, managers, access policy, audit enablement, and recent syscall records.
- KernelService audit records use `kernel.<queue>.<operation>` names; robot skill audit records remain owned by SkillExecutor.

## Commands Run

```bash
find /home/ubuntu/AIOS/aios -maxdepth 2 -type f | sort > /tmp/aios_kernel_files.txt
find agentic_runtime_src/agentic_os/kernel -maxdepth 4 -type f | sort > /tmp/agentic_kernel_files.txt
git rev-parse HEAD
git status --short
python --version
pytest -q
python scripts/check_forbidden_imports.py
pytest -q tests/test_storage_manager.py tests/test_architecture_module_layout.py
pytest -q tests/test_agentic_os_kernel_modules.py tests/test_runtime_kernel_wrappers.py
pytest -q tests/test_access_manager.py
pytest -q tests/test_kernel_hooks_queues.py
pytest -q tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py tests/test_agentic_os_kernel_modules.py
pytest -q tests/test_kernel_scheduler_threads.py tests/test_kernel_scheduler_robot_lanes.py
pytest -q tests/test_runtime_kernel_wrappers.py tests/test_kernel_session_runner.py
pytest -q tests/test_agentic_os_kernel_modules.py tests/test_kernel_scheduler_threads.py tests/test_kernel_manager_contracts.py
pytest -q tests/test_kernel_llm_core.py tests/test_llm_client.py
pytest -q tests/test_context_manager.py tests/test_kernel_generation_context.py tests/test_kernel_scheduler_robot_lanes.py
pytest -q tests/test_kernel_memory_manager_v2.py tests/test_memory.py tests/test_memory_provider.py tests/test_runtime_kernel_wrappers.py
pytest -q tests/test_kernel_storage_syscalls.py tests/test_storage_manager.py tests/test_runtime_kernel_wrappers.py
pytest -q tests/test_tool_manager.py tests/test_kernel_tool_dynamic_loading.py tests/test_agentic_os_kernel_modules.py
pytest -q tests/test_runtime_kernel_service.py tests/test_runtime_kernel_wrappers.py tests/test_sdk.py tests/test_skill_executor.py
pytest -q
python scripts/check_forbidden_imports.py
pytest -q tests/test_bridge_manager.py tests/test_ros2_cli_bridge_client.py tests/test_capability_registry.py
pytest -q
python scripts/check_forbidden_imports.py
pytest -q tests/test_sdk.py tests/test_runtime_kernel_service.py tests/test_skill_executor.py
pytest -q
python scripts/check_forbidden_imports.py
pytest -q tests/test_kernel_e2e_syscall_flow.py tests/test_kernel_observability.py tests/test_robot_safety_regression.py
pytest -q tests/test_sdk.py tests/test_skill_executor.py tests/test_room_inspection_flow.py tests/test_robot_photographer_agent.py tests/test_runtime_kernel_service.py
pytest -q
python scripts/check_forbidden_imports.py
bash scripts/run_tests.sh
AGENTIC_HOME=/tmp/agentic_pr15_demo AGENTIC_VAR=/tmp/agentic_pr15_demo/var AGENTIC_ETC=/tmp/agentic_pr15_demo/etc python -m agentic_runtime.cli bridge install --profile ros2_default --dry-run --json
bash scripts/install_to_opt_agentic.sh
source /opt/agentic/setup.bash
/opt/agentic/bin/agentic status --json
DEPTH_CAMERA_TYPE=aurora need_compile=False ros2 launch peripherals depth_camera.launch.py
ros2 topic info /depth_cam/rgb0/image_raw -v
timeout 8 ros2 topic echo --once /depth_cam/rgb0/image_raw sensor_msgs/msg/Image --field header
AGENTIC_PHOTO_EVIDENCE_ROOT=/opt/agentic/var/evidence/photos AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT=/opt/agentic/var/storage/robot_photographer_agent /opt/agentic/bin/agentic photo --real --json 拍一张照片
python - <<'PY'
from pathlib import Path
from PIL import Image
for path in [
    Path('/opt/agentic/var/evidence/photos/photo_20260617_135737_capture_4f697c881380.png'),
    Path('/opt/agentic/var/storage/robot_photographer_agent/runs/sess_bbe925939d7a/photos/01_photo.png'),
]:
    with Image.open(path) as img:
        print(path, img.size, img.mode)
PY
```

## Results

- Agentic commit: `2065ce4a0daa4fb3fb72d2e02e983f0f7ac8a8ed`
- AIOS commit: `5de61c9ad9c94ff6db7879e3a5f3d787f73b4726`
- Python: `Python 3.10.12`
- Runtime tests: `130 passed in 19.11s`
- Forbidden import/static guard: `forbidden import/static guard ok`
- PR-01 targeted storage/layout tests: `17 passed in 0.78s`
- PR-01 compatibility tests: `11 passed in 0.76s`
- PR-01 full runtime tests: `134 passed in 23.00s`
- PR-02 targeted access tests: `7 passed in 0.72s`
- PR-02 compatibility tests: `11 passed in 1.09s`
- PR-02 full runtime tests: `141 passed in 20.20s`
- PR-03 targeted hooks tests: `5 passed in 0.57s`
- PR-03 full runtime tests: `146 passed in 19.27s`
- PR-04 targeted syscall tests: `13 passed in 0.57s`
- PR-04 full runtime tests: `154 passed in 18.45s`
- PR-05 targeted scheduler tests: `10 passed in 0.90s`
- PR-05 runtime wrapper/session tests: `7 passed in 1.30s`
- PR-05 full runtime tests: `164 passed in 21.10s`
- PR-06 targeted manager contract tests: `16 passed in 0.82s`
- PR-06 manager cleanup tests: `5 passed in 0.45s`
- PR-06 full runtime tests: `169 passed in 19.12s`
- PR-07 targeted LLM tests: `12 passed in 0.44s`
- PR-07 optional dependency import check: openai/litellm/transformers/chromadb/mcp/redis all `False`
- PR-07 full runtime tests: `176 passed in 18.67s`
- PR-08 targeted context tests: `9 passed in 0.67s`
- PR-08 full runtime tests: `180 passed in 18.87s`
- PR-09 targeted memory tests: `15 passed in 0.62s`
- PR-09 optional dependency import check: chromadb/sentence_transformers/qdrant_client/numpy/sklearn all `False`
- PR-09 full runtime tests: `187 passed in 18.95s`
- PR-10 targeted storage tests: `20 passed in 0.62s`
- PR-10 full runtime tests: `195 passed in 19.34s`
- PR-11 targeted tool tests: `12 passed in 0.56s`
- PR-11 full runtime tests: `200 passed in 19.14s`
- PR-12 targeted KernelService/SDK/SkillExecutor tests: `24 passed in 6.80s`
- PR-12 full runtime tests: `206 passed in 19.69s`
- PR-12 forbidden import/static guard: `forbidden import/static guard ok`
- PR-13 targeted bridge/capability tests: `22 passed in 2.80s`
- PR-13 full runtime tests: `212 passed in 19.80s`
- PR-13 forbidden import/static guard: `forbidden import/static guard ok`
- PR-14 targeted SDK/KernelService/SkillExecutor tests: `22 passed in 6.73s`
- PR-14 full runtime tests: `216 passed in 19.73s`
- PR-14 forbidden import/static guard: `forbidden import/static guard ok`
- PR-15 targeted E2E/observability/safety tests: `8 passed in 1.94s`
- PR-15 compatibility tests: `38 passed in 12.57s`
- PR-15 full runtime tests: `224 passed in 21.28s`
- PR-15 forbidden import/static guard: `forbidden import/static guard ok`
- Final unified checks: `forbidden import/static guard ok`; `filesystem layout guard ok`; `224 passed in 21.64s`; `Agentic OS MVP checks passed.`
- Bridge CLI dry-run demo: `success: true`, `dry_run: true`, `install_result.status: install_planned`; no colcon install command executed.
- `/opt/agentic` deployment: `Agentic OS installed to /opt/agentic`.
- Installed import check: `agentic_runtime=/opt/agentic/lib/python3/agentic_runtime/__init__.py`; `agentic_os=/opt/agentic/agentic_os/__init__.py`.
- Installed status check: AgenticOS reported `agenticd: running`, `ros_bridge: mock`, and expected skills ready.
- First real photo attempt reached the real bridge and failed truthfully with `CAMERA_UNAVAILABLE` because no fresh camera frame was available.
- Camera readiness fix: started Aurora 930 driver with `DEPTH_CAMERA_TYPE=aurora` and confirmed `/depth_cam/rgb0/image_raw` had `Publisher count: 1` and a frame header with `frame_id: rgb_camera_link`.
- Real installed app validation: `/opt/agentic/bin/agentic photo --real --json 拍一张照片` completed successfully through the real bridge and real camera.
- Real capture result: `perception_backend_status: CAPTURED`, topic `/depth_cam/rgb0/image_raw`, `640x400`, `bgr8`, audit IDs `audit_009543` and `audit_009544`.
- Real raw evidence: `/opt/agentic/var/evidence/photos/photo_20260617_135737_capture_4f697c881380.png` and matching JSON metadata.
- Real app output: `/opt/agentic/var/storage/robot_photographer_agent/runs/sess_bbe925939d7a/photos/01_photo.png` and matching JSON metadata.
- Image verification: both raw evidence and app output opened as `640x400 RGB` PNG files.

## Risks / Notes

- The current tree contains pre-existing untracked files under `/home/ubuntu/Agentic_OS_ROS_publish/docs/`; they are not part of PR-00.
- Existing `find` output includes `__pycache__` files under `agentic_os/kernel`; this is recorded as baseline noise and not changed.
- Real bridge build/install execution was not run; it remains correctly gated behind `AGENTIC_ALLOW_BRIDGE_INSTALL=1`.
- Full real robot motion acceptance scripts were not run; the post-port hardware validation covered real bridge services and real camera capture only.
- The bridge CLI dry-run uses the configured bridge roots from runtime config; in this workspace those roots resolve to `/opt/agentic/...`.
- Sourcing `/opt/agentic/setup.bash` emits local `/opt/ros/humble` setup warnings about `/home/ubuntu/setup.sh` and `/home/ubuntu/local_setup.sh`; commands continued and real capture succeeded.
- The Aurora camera driver must be running before `agentic photo --real`; otherwise the bridge returns structured `CAMERA_UNAVAILABLE`.

## Resume Point

PR-00 through PR-15 are complete from `/home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src`.
