# Codex Kernel Port Baseline

- PR: PR-00
- Date: 2026-06-17
- Agentic OS ROS repo: `/home/ubuntu/Agentic_OS_ROS_publish`
- AIOS reference repo: `/home/ubuntu/AIOS`
- Agentic commit: `2065ce4a0daa4fb3fb72d2e02e983f0f7ac8a8ed`
- AIOS commit: `5de61c9ad9c94ff6db7879e3a5f3d787f73b4726`
- Python version: `Python 3.10.12`
- Initial git status: three pre-existing untracked files under repository `docs/`

## Baseline Commands

```bash
find /home/ubuntu/AIOS/aios -maxdepth 2 -type f | sort > /tmp/aios_kernel_files.txt
find agentic_runtime_src/agentic_os/kernel -maxdepth 4 -type f | sort > /tmp/agentic_kernel_files.txt
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
pytest -q
python scripts/check_forbidden_imports.py
```

## Results

- AIOS kernel reference files: 43 files at max depth 2.
- Agentic kernel files: 65 files at max depth 4, including existing `__pycache__` files present in the working tree.
- Runtime test baseline: `130 passed in 19.11s`.
- Forbidden import/static guard: `forbidden import/static guard ok`.

## AIOS Kernel Directories

```text
/home/ubuntu/AIOS/aios
/home/ubuntu/AIOS/aios/config
/home/ubuntu/AIOS/aios/context
/home/ubuntu/AIOS/aios/hooks
/home/ubuntu/AIOS/aios/hooks/modules
/home/ubuntu/AIOS/aios/hooks/stores
/home/ubuntu/AIOS/aios/hooks/types
/home/ubuntu/AIOS/aios/hooks/utils
/home/ubuntu/AIOS/aios/llm_core
/home/ubuntu/AIOS/aios/memory
/home/ubuntu/AIOS/aios/memory/providers
/home/ubuntu/AIOS/aios/scheduler
/home/ubuntu/AIOS/aios/storage
/home/ubuntu/AIOS/aios/storage/filesystem
/home/ubuntu/AIOS/aios/syscall
/home/ubuntu/AIOS/aios/syscall/types
/home/ubuntu/AIOS/aios/terminal
/home/ubuntu/AIOS/aios/tool
/home/ubuntu/AIOS/aios/tool/virtual_env
/home/ubuntu/AIOS/aios/utils
/home/ubuntu/AIOS/aios/utils/commands
```

## Agentic Kernel Directories

```text
agentic_os/kernel
agentic_os/kernel/capability
agentic_os/kernel/context
agentic_os/kernel/device_arbitration
agentic_os/kernel/memory
agentic_os/kernel/model_library
agentic_os/kernel/perception
agentic_os/kernel/scheduler
agentic_os/kernel/skill_library
agentic_os/kernel/storage
agentic_os/kernel/system_call
agentic_os/kernel/tool
agentic_os/kernel/world_model
```

## Initial Gaps

- Access manager package is not present yet.
- AIOS-style hooks/module queue package is not present yet.
- Typed async syscall family and queue-backed syscall execution are not present yet.
- Scheduler is still a lightweight in-memory request scheduler, not module processing threads.
- LLM core, generation context, memory v2, storage syscalls, and dynamic tool loading remain PR-07 through PR-11 work.
- Runtime KernelService, bridge lifecycle, SDK compatibility layer, and E2E hardening remain PR-12 through PR-15 work.
