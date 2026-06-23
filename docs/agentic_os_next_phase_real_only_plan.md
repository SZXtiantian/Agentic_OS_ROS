# Agentic OS 下一阶段计划：全真实后端与零模拟路径收敛

> 目标仓库：`/home/ubuntu/Agentic_OS_ROS_publish`  
> 目标分支策略：**不创建新分支，直接在当前主分支按模块 commit，并最终 push 到主分支**  
> 核心原则：所有成功路径必须来自真实 provider/backend/service；缺依赖时只能 fail-fast 或返回稳定错误码，不能伪造成功。

---

## 1. 当前代码状态摘要

更新后的代码已经完成了重要推进：

- 已新增 `context` syscall、`skill` syscall、typed query/factory/queue/SDK facade。
- `context` 已有 SQLite provider，支持 `put/get/delete/list/snapshot/recover/compact/clear`。
- `memory` 已有 SQLite + FTS5 provider，支持 `remember/add/search/get/update/delete/list/export/import`。
- `storage` 已有真实本地文件系统、版本历史和 FTS 检索。
- `tool` 已有真实 builtin，例如 calculator、format_report、file_digest，并禁止 robot/ROS 能力伪装为普通 tool。
- `skill` 已接 RuntimeSkillBackend，具备 `call/list/describe/status/cancel` 入口。
- 当前测试可通过，但测试通过不能证明“全真实”，因为默认 runtime、CLI、session、app invoker、ROS bridge、部分配置和测试仍保留模拟路径。

下一阶段不再优先扩展接口数量，而是把所有默认路径收敛到真实后端，并用 guard tests 防止回退。

---

## 2. 不可变约束

1. **禁止模拟成功路径**：生产路径不得使用 mock/fake/stub/dummy/dummy-success 等形式返回成功。
2. **真实依赖缺失必须可见**：缺 ROS2、缺 LLM provider、缺 human backend、缺 runtime、缺 credential 时，返回稳定错误码，并进入 `status/health/audit`。
3. **不破坏兼容接口**：保留 `ctx.robot`、`ctx.memory`、`ctx.storage`、`ctx.human`、`ctx.report`、`ctx.call_skill` 和新增 `ctx.kernel.*`。
4. **不创建分支**：直接在主分支提交；每完成一个模块且测试通过后单独 commit。
5. **凭据安全**：不得把 API key/token 写入代码、配置、文档、日志、commit message 或测试快照；只能读取环境变量或 credential helper。
6. **所有危险操作必须 access/intervention/audit**：robot motion、human ask、storage delete/rollback/share、tool load/unload、memory export/import/delete、LLM 外部调用等。
7. **统一响应模型**：public syscall 统一返回 `KernelResponse` 或兼容 dict：`success`、`data/response_message`、`error_code`、`metadata`。

---

## 3. 目标架构闭环

所有 namespace 必须落到同一条闭环：

```text
SDK facade
  -> typed Query
  -> typed Syscall
  -> KernelQueueName / queue store
  -> Scheduler lane processor
  -> Manager.address_request
  -> Real Provider / Real Backend / Real External Service
  -> KernelResponse + audit/status/metrics
```

不得出现只写 SDK wrapper、不接 manager/backend 的接口。不得出现 manager 返回固定成功数据的空实现。

---

## 4. 下一阶段工程包

### A. 清理生产模拟路径与默认配置

优先处理这些文件：

```text
agentic_runtime_src/configs/agentic.yaml
agentic_runtime_src/agentic_runtime/types.py
agentic_runtime_src/agentic_runtime/server.py
agentic_runtime_src/agentic_runtime/cli.py
agentic_runtime_src/agentic_runtime/nl_cli.py
agentic_runtime_src/agentic_runtime/nl_gateway.py
agentic_runtime_src/agentic_runtime/photo_cli.py
agentic_runtime_src/agentic_runtime/app_invoker.py
agentic_runtime_src/agentic_runtime/scheduler/session_runner.py
agentic_runtime_src/agentic_runtime/session/manager.py
agentic_runtime_src/agentic_runtime/session/models.py
agentic_runtime_src/agentic_runtime/kernel_service/server.py
agentic_runtime_src/agentic_runtime/kernel_service/schemas.py
agentic_runtime_src/agentic_runtime/ros_bridge_client/client.py
agentic_runtime_src/agentic_runtime/ros_bridge_client/__init__.py
agentic_runtime_src/agentic_runtime/skill_executor/executor.py
```

要求：

- `RuntimeServer.create()` 默认不得进入模拟后端。
- CLI 不再提供默认模拟运行；若保留兼容参数，只能报错说明该模式已禁用。
- `SessionRecord`、`task_input`、`AppInvoker` 不再默认注入模拟字段。
- skill backend 默认值不得是模拟类型；manifest 缺 backend 时应失败或要求显式真实 backend。
- `ros_bridge_client` 生产入口只允许真实 bridge client；模拟 client 不得从生产包导出。
- 默认配置统一为真实 `cli`/real runtime；旧的演示配置移到 archived docs，不参与运行。

验收：新增 `tests/guards/test_no_simulated_production_paths.py`，扫描生产路径，禁止模拟后端 import、默认值、CLI 默认、配置默认和伪成功文本。

---

### B. ROS / Robot runtime 真实化

目标：robot/perception/arm/gripper 只能通过真实 ROS2 bridge 或真实 runtime service 执行。

要求：

- `create_ros_bridge_client(config)` 只创建真实 client。
- ROS2 CLI bridge 缺 `ros2` 命令、缺 service/action/topic、超时时返回稳定错误码：`ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_TIMEOUT`、`ROS_RESULT_INVALID`。
- `robot.navigate_to`、`robot.inspect_area`、`perception.capture_photo`、`arm.move_named`、`gripper.set` 必须要求权限和 audit。
- real integration tests 使用真实 ROS2 环境变量启用；环境缺失时标记为未验证，不得用模拟成功替代。

---

### C. Human backend 真实化

目标：`human.ask` 不能永久阻塞 worker，不能伪造用户回答。

要求：

- 实现真实 `RuntimeHumanBackend`，可接 CLI/TUI/HTTP/WebSocket/队列中的至少一种真实人机通道。
- `human.ask` 支持 timeout、cancel、correlation id、审计记录。
- 缺 human backend 时返回 `HUMAN_BACKEND_UNAVAILABLE`；超时返回 `HUMAN_TIMEOUT`；取消返回 `HUMAN_CANCELLED`。
- 不得自动填默认回答。

---

### D. 权限、intervention、audit 收紧

当前 robot/human backend 存在自动补默认权限的风险。下一阶段必须改成：

```text
没有显式权限 -> ACCESS_DENIED
有权限但需要审批 -> INTERVENTION_REQUIRED / APPROVED / DENIED
已执行 -> audit event + metadata
```

重点文件：

```text
agentic_runtime_src/agentic_runtime/kernel_service/robot_backend.py
agentic_runtime_src/agentic_runtime/kernel_service/human_backend.py
agentic_os/kernel/*/manager.py
```

要求：

- backend 不能自己补高危权限。
- 权限从 app manifest / syscall metadata / access manager 进入统一判断。
- 审计记录包含 agent、operation、resource、permission、decision、duration、error_code。

---

### E. Cancel / timeout 正确性

优先修复 `KernelQueueStore.remove()` 的 cancel 语义，避免找不到目标时误移除其他 syscall。

要求：

- `cancel(syscall_id)` 只能取消精确匹配的 syscall。
- 找不到返回 `SYSCALL_NOT_FOUND`。
- 正在运行的 LLM/tool/skill/human 请求需要 active task registry，能传递 cancel signal。
- timeout 必须从 SDK metadata 一路传到 manager/backend。
- 新增并发测试：多请求排队、取消中间请求、取消运行中请求、取消不存在请求。

---

### F. LLM provider 真实化

目标：LLM 不得产生伪响应。

要求：

- OpenAI-compatible provider：真实 chat/complete/embed/status。
- LiteLLM provider：真实 chat/complete/embed；缺依赖或配置时稳定失败。
- HF/local provider：如果不能真实运行，就不要声明为可用 provider；status 明确 `UNAVAILABLE`。
- provider config 必填项：base_url/api_key/model/timeout/embed_model 等按 backend 校验。
- LLM 外部调用进入 access/audit。
- 缺配置返回 `LLM_PROVIDER_UNCONFIGURED`，缺依赖返回 `LLM_PROVIDER_DEPENDENCY_MISSING`，远端失败返回 `LLM_PROVIDER_ERROR`。

---

### G. Storage / Memory / Context 收尾硬化

这些模块已经比较实，但还需补验收闭环：

- storage `read/list/write/delete/share/rollback` 全部接 access/audit。
- storage `share` 改为持久化 share registry，不能只保存在内存。
- storage semantic retrieve 只有接真实 embedding/vector provider 后才能标记为 semantic；否则只能声明 lexical/FTS。
- memory export/import/delete 接权限和 audit。
- context compact 明确语义：结构压缩/大小裁剪，而不是 LLM 语义总结，除非接真实 LLM provider。
- 所有 provider status 显示 storage path、DB path、FTS availability、last_error。

---

### H. App 与文档收敛

要求：

- `app_template` 保持 kernel smoke，但不要把缺 runtime 的 skill/report 伪造成成功。
- 新增 real integration app 或 test profile：真实 runtime + ROS2 + human + LLM provider 可用时全链路成功。
- 文档中旧的模拟命令移到 archive 或明确标注“历史设计，不可作为当前运行方式”。
- `docs/kernel_syscalls.md` 更新真实 provider 配置、错误码、权限表、验证命令。

---

## 5. 测试矩阵

### 必须新增或更新

```text
tests/guards/test_no_simulated_production_paths.py
tests/kernel/test_queue_cancel_correctness.py
tests/kernel/test_real_backend_dependency_failures.py
tests/kernel/test_access_denied_without_permissions.py
tests/kernel/test_audit_events.py
tests/llm/test_real_provider_config_validation.py
tests/runtime/test_runtime_server_real_defaults.py
tests/runtime/test_cli_real_defaults.py
tests/integration/test_real_ros_bridge_contract.py
tests/integration/test_real_human_backend_contract.py
tests/integration/test_real_llm_provider_contract.py
```

### 推荐验证命令

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pytest -q
python -m pytest tests/guards -q
python -m pytest tests/kernel -q
python -m pytest tests/runtime -q
python -m pytest tests/llm -q
python -m pytest tests/integration -q
python scripts/check_no_simulated_backends.py
rg -n "mock|fake|stub|dummy|allow_mock|ros_bridge_mode: mock|RuntimeServer\.create\(mock=True\)" \
  agentic_os agentic_runtime ../agentic_apps --glob '!**/__pycache__/**'
```

如果确有历史文档或负向测试需要保留相关词，必须建立 allowlist，并说明它们不会进入生产执行路径。

---

## 6. Commit 顺序

不创建新分支。每个工程包完成、测试通过后单独 commit：

```text
fix(runtime-config): disable simulated backends in defaults
refactor(runtime-server): require real runtime backend by default
refactor(ros-bridge): remove simulated client from production path
fix(access): deny robot and human calls without explicit permissions
fix(kernel-queue): correct syscall cancellation semantics
feat(human): add real human backend timeout and cancel contract
feat(llm): enforce real provider configuration and embeddings
fix(storage): persist share registry and audit all dangerous operations
test(guards): add no simulated production path checks
test(integration): add real backend contract tests
docs(kernel): document real provider requirements and error codes
```

最终：

```bash
git status
git log --oneline -n 20
git push origin HEAD
```

---

## 7. 验收标准

1. 当前主分支上按模块存在清晰 commit。
2. `RuntimeServer.create()`、CLI、app invoker、session 默认不再进入模拟路径。
3. 生产代码不导出、不默认创建、不伪成功返回模拟 backend。
4. 缺真实依赖时返回稳定错误码，并出现在 status/audit。
5. robot/human/LLM/storage 危险操作没有权限时拒绝。
6. cancel/timeout 对排队和运行中 syscall 都可靠。
7. OpenAI-compatible 或配置指定的真实 LLM provider 能真实请求；缺配置失败清晰。
8. ROS2 bridge 真实 contract test 可在真实环境运行；环境缺失时报告未验证，不以模拟替代。
9. human.ask 接真实人机后端；无后端、超时、取消均可测。
10. 全量测试通过，并提供命令证据。
11. push 到主分支完成；如果 push 因权限或保护策略失败，报告 commit hash 和失败原因。

---


