# Agentic OS 基础框架完成阶段开发文档（Real-Only / Loop Engineering / Single Local Commit）

## 0. 文档目的

本文件用于交给 Codex 执行下一轮工程实现，目标不是再做零散补丁，而是把 Agentic OS 的基础框架完整搭建成一个 **真实 provider/backend 驱动、可调度、可观测、可测试、可交付** 的系统。

当前代码已经完成了重要进展：context、memory、storage、tool、skill、LLM、robot/human capability 的 kernel syscall 轮廓已经成型，生产路径中的 mock 成功返回大多已经禁止，默认运行已经转向真实 backend 或 fail-fast。下一阶段要完成的是 **框架收口**：

1. 删除生产 API 中残留的 mock/simulated surface。
2. 建立真实 backend/provider 的统一 contract。
3. 让 runtime、kernel、SDK、CLI、配置、测试、文档形成一致的 real-only 基础框架。
4. 把真实集成验证纳入工程闭环，而不是仅验证“缺依赖时能失败”。
5. 用 guard tests 防止未来回退到 mock、fake、stub、dummy 或空壳成功路径。

本阶段完成后，Agentic OS 应该具备稳定的基础框架：应用可以通过 `ctx.kernel.*` 与 `ctx.*` 访问真实 syscall 能力；缺少真实依赖时，系统以稳定错误码、status、audit 明确失败；具备可复现的测试与验证证据。

---

## 1. 当前状态判断

基于上一轮代码审查，当前状态如下：

| 能力面 | 当前状态 | 下一阶段目标 |
|---|---|---|
| Context | SQLite provider、syscall、SDK、测试基本完成 | 收口 provider contract、status、audit、docs |
| Memory | SQLite + FTS5 已实现 | 补齐导入/导出安全、权限、status、guard |
| Storage | 本地 FS + history + FTS + share registry | 强化危险操作 audit；semantic retrieve 只在真实 embedding/vector provider 可用时声明 |
| Tool | builtin 工具真实执行；禁止 robot/ROS 伪装 tool | 删除模拟 surface；完善 manifest 权限与 status |
| Skill | syscall/backend 接入 runtime | 完成真实 runtime e2e contract；删除模拟 flag |
| Robot/ROS2 | CLI bridge real-only；缺 ROS2 返回稳定错误 | 真实 ROS2 contract tests 与配置校验 |
| Human | file queue 人机通道存在，支持 timeout/cancel | 接入真实 intervention/operator provider，完成端到端 |
| LLM | OpenAI-compatible 路径真实，缺配置 fail-fast | 完整 provider catalog；不可用 provider 不得声明可用 |
| Runtime/CLI | 默认不 mock，但仍有 `mock` 参数/flag | 删除生产 mock/simulated surface |
| Tests | 单测强，真实集成 gate 存在 | 加强 real integration、no-simulated guard、CI 分类 |
| Docs | 有基本说明 | 建立完整基础框架文档、配置矩阵、运行手册 |

---

## 2. 本阶段不可妥协原则

### 2.1 Real-only 原则

生产代码中不得保留任何会导致伪成功的路径：

- 禁止 mock/fake/stub/dummy/simulated backend 成功返回。
- 禁止默认 fallback 到本地假数据。
- 禁止配置缺失时自动伪造 LLM、ROS、human、tool、skill 响应。
- 禁止把 robot/ROS/moveit/nav2/cmd_vel 等能力包装成普通 tool 绕过权限。
- 禁止测试用伪成功替代真实集成验证。

允许的行为只有两类：

1. **真实成功**：真实 provider/backend/service 被配置、健康、权限通过，并执行完成。
2. **稳定失败**：真实依赖缺失、配置错误、权限不足、intervention 未批准、timeout、cancel、远端失败时，返回统一错误码并记录 status/audit。

### 2.2 Production surface 清洁原则

上一版中部分生产 API 仍保留 `mock`、`--mock`、`SIMULATED_BACKEND_DISABLED` 等兼容 surface。下一阶段需要清理为：

- CLI 不再暴露 `--mock`。
- RuntimeServer/AppInvoker/Session/task schema 不再接受 `mock` 字段。
- 生产模块不 import/export simulated client。
- 配置 schema 不接受 `ros_bridge_mode: mock`、`backend: mock`。
- 相关历史说明可以移入 archive 文档，但不能作为当前运行方式出现。

如需保留历史迁移错误码，可以保留 `SIMULATED_BACKEND_DISABLED` 作为兼容错误码，但不得作为新的公开操作入口。

### 2.3 Loop Engineering 原则

Codex 执行时必须采用闭环工程方法：

```text
Inspect → Specify → Plan → Implement small vertical slice → Test → Observe → Patch → Re-run → Evidence
```

每个循环只处理一个明确能力面，例如：

- 删除 CLI mock surface。
- 收口 runtime config schema。
- 实现 human intervention provider。
- 修正 LLM provider catalog。
- 增加 real ROS2 contract tests。

每个循环必须留下：

1. 改动范围。
2. 运行命令。
3. 失败输出或验证输出。
4. 修复动作。
5. 当前阶段证据记录；循环内不得提交 commit。

---

## 3. 总体架构目标

基础框架最终应形成以下闭环：

```text
App / SDK
  ↓
AgentContext / ctx.kernel.* / ctx.*
  ↓
Typed Query
  ↓
Typed Syscall
  ↓
KernelQueueName / Scheduler Lane
  ↓
Manager.address_request()
  ↓
Real Provider / Backend / Bridge / Service
  ↓
KernelResponse
  ↓
Status / Audit / Metrics / Events
```

所有 namespace 都必须符合统一契约：

| Namespace | 必须具备 |
|---|---|
| context | typed query/syscall、persistent provider、snapshot/recover、status/audit |
| memory | SQLite/FTS 或真实 vector provider、CRUD、import/export、权限 |
| storage | safe local FS、versioning、FTS/index、share registry、danger audit |
| tool | real builtin、manifest registry、禁止机器人伪装、权限/status |
| skill | runtime backend、list/describe/call/status/cancel、权限 |
| llm | real provider catalog、chat/complete/embed/status/cancel、配置校验 |
| robot | real ROS2/CLI/service/action bridge、权限、timeout/cancel |
| human | real operator channel、intervention、timeout/cancel、audit |
| access | deny-by-default、intervention provider、audit trail |
| runtime | real default、dependency preflight、no simulated surface |
| CLI | real-only commands、lazy import、明确错误 |
| tests | unit/integration/e2e/contract/guard 分类 |

---

## 4. 开发包划分

### 包 A：删除生产 mock/simulated surface

#### 目标

生产入口中不再暴露 mock 或 simulated 运行模式。系统启动时只接受真实 provider/backend 配置。

#### 范围

重点检查并修改：

```text
agentic_runtime_src/agentic_runtime/server.py
agentic_runtime_src/agentic_runtime/cli.py
agentic_runtime_src/agentic_runtime/photo_cli.py
agentic_runtime_src/agentic_runtime/nl_cli.py
agentic_runtime_src/agentic_runtime/nl_gateway.py
agentic_runtime_src/agentic_runtime/app_invoker.py
agentic_runtime_src/agentic_runtime/session.py
agentic_runtime_src/agentic_runtime/types.py
agentic_runtime_src/agentic_runtime/kernel_service/server.py
agentic_runtime_src/agentic_runtime/kernel_service/schema.py
agentic_runtime_src/agentic_runtime/ros_bridge_client/client.py
agentic_runtime_src/configs/*.yaml
```

#### 要求

- 删除 CLI `--mock`。
- 删除 task/session/app input 中 `mock` 字段。
- 删除 `RuntimeServer.create(mock=...)` 公开参数；如需内部兼容，必须不可由用户触发。
- 配置 parser 遇到 mock/simulated 直接 schema validation error。
- `ros_bridge_mode` 只允许真实模式，如 `cli`、`service`、`action`、`http`、`websocket`。
- `backend: mock` 不再是合法配置。
- no-simulated guard tests 扫描生产代码与配置。

#### 验收

```bash
PYTHONPATH=. pytest -q tests/test_no_simulated_production_paths.py
PYTHONPATH=. pytest -q tests/test_runtime_real_defaults.py
```

---

### 包 B：真实 provider/backend contract 与 preflight

#### 目标

建立统一 provider/backend contract，使所有真实依赖都能被 preflight、status、health、audit 识别。

#### 新增或统一接口

每个 provider/backend 至少实现：

```python
class ProviderContract:
    name: str
    kind: str
    capabilities: list[str]

    def validate_config(self) -> ProviderValidationResult: ...
    def status(self) -> ProviderStatus: ...
    def health(self) -> ProviderHealth: ...
    def close(self) -> None: ...
```

结果模型应包含：

```text
available: bool
configured: bool
healthy: bool
error_code: str | None
missing: list[str]
details: dict
```

#### 应用于

- LLM provider
- ROS bridge
- Human channel/intervention provider
- Storage index/semantic provider
- Memory vector provider
- Tool manifest registry
- Skill runtime backend

#### 验收

- `KernelService.status()` 能列出所有 namespace 的 provider 状态。
- 缺配置时返回稳定错误，不触发懒加载假成功。
- provider 不可用不影响其他 namespace 启动，但对应 syscall 必须稳定失败。

---

### 包 C：权限、intervention、audit 收口

#### 目标

所有危险操作都必须进入 access/intervention/audit 链路，且 backend 不得自动补高危权限。

#### 必须覆盖的危险操作

| 能力 | 操作 |
|---|---|
| robot | navigate/move/arm/gripper/cmd_vel/action send |
| human | ask/notify/operator approval |
| storage | delete/rollback/share/mount/write outside safe root |
| memory | export/import/delete/bulk delete |
| tool | load_manifest/unload/register external tool |
| skill | robot/human/system skill call |
| llm | external provider call、embedding call、context export |
| context | clear/recover large checkpoint |

#### 要求

- AccessManager deny-by-default。
- 权限来自 app manifest / syscall metadata / verified runtime identity。
- backend 不允许自动补默认权限。
- intervention provider 必须真实：file queue、console、HTTP/WebSocket/operator queue 三者至少实现一种。
- audit entry 包含 syscall_id、agent_name、operation、permission、decision、reason、timestamp、provider、metadata hash。
- audit 可检索、可导出。

#### 验收

```bash
PYTHONPATH=. pytest -q tests/test_access_denied.py
PYTHONPATH=. pytest -q tests/test_audit_trail.py
PYTHONPATH=. pytest -q tests/test_intervention_provider.py
```

---

### 包 D：cancel、timeout、active task registry

#### 目标

所有长耗时 syscall 都有可追踪的生命周期，支持 timeout/cancel/status。

#### 范围

- LLM chat/complete/embed
- skill.call
- tool.call
- human.ask
- robot/perception/arm action
- storage large retrieve/index
- memory import/export

#### 要求

- `KernelQueueStore.remove(syscall_id)` 精确取消。
- manager 维护 active task registry。
- cancel 找不到任务返回 `SYSCALL_NOT_FOUND`。
- 已完成任务 cancel 返回 `SYSCALL_ALREADY_COMPLETED` 或兼容稳定错误。
- timeout 必须释放 worker，不得造成永久阻塞。
- status 能查询 active/running/cancelled/timed_out/completed。

#### 验收

```bash
PYTHONPATH=. pytest -q tests/test_kernel_cancel.py
PYTHONPATH=. pytest -q tests/test_timeout_contracts.py
```

---

### 包 E：真实 LLM provider 完成

#### 目标

LLM namespace 只声明真实可用 provider；不可用 provider 不得出现在可用列表中。

#### 必须实现

- `ctx.kernel.llm.chat`
- `ctx.kernel.llm.complete`
- `ctx.kernel.llm.embed`
- `ctx.kernel.llm.status`
- `ctx.kernel.llm.cancel`

#### Provider 策略

至少保证以下之一完整可用：

1. OpenAI-compatible provider：`base_url`、`api_key`、`model`、`embedding_model`。
2. LiteLLM provider：真实调用 LiteLLM 支持的后端。
3. Local provider：Ollama / vLLM / llama.cpp / transformers 中选择一个真实实现。
4. HuggingFace provider：只有 transformers pipeline 或 inference endpoint 真实可用时才声明支持。

如果某 provider 尚未真实实现：

- 从 docs 的可用列表移除。
- status 返回 unsupported/unavailable。
- tests 不得假装它可用。

#### 验收

- 无配置：`LLM_PROVIDER_UNCONFIGURED`。
- 依赖缺失：`LLM_PROVIDER_DEPENDENCY_MISSING`。
- 远端失败：`LLM_PROVIDER_REQUEST_FAILED`。
- 真实配置存在时，integration test 能发起真实请求。
- embed 必须真实返回向量或明确 unsupported。

---

### 包 F：真实 ROS2 / robot integration

#### 目标

robot/perception/arm/gripper 能力通过真实 ROS2 CLI/service/action/topic 执行或明确失败。

#### 必须完成

- preflight 检查 `ros2` CLI 是否存在。
- 检查 service/action/topic 名称、类型、超时配置。
- robot status 返回 ROS graph 依赖状态。
- 缺服务时返回 `ROS_SERVICE_UNAVAILABLE`。
- 缺 action 时返回 `ROS_ACTION_UNAVAILABLE`。
- 缺 CLI 时返回 `ROS_BRIDGE_UNAVAILABLE`。
- 所有 motion 操作必须有 permission + intervention/audit。

#### Real integration tests

通过环境变量启用：

```bash
AGENTIC_VERIFY_REAL_ROS2=1 PYTHONPATH=. pytest -q tests/test_real_ros2_integration.py
```

未启用时，测试可 skip，但必须报告：

```text
UNVERIFIED_REAL_DEPENDENCY: ROS2
```

不得用模拟 ROS 成功替代。

---

### 包 G：真实 human/operator channel

#### 目标

human.ask 通过真实 operator channel 完成请求、批准、回答、取消、超时。

#### 推荐实现

至少实现一种：

1. FileQueueHumanProvider：JSONL 请求队列 + answer CLI。
2. ConsoleHumanProvider：终端交互。
3. HTTPHumanProvider：HTTP endpoint 轮询/回调。
4. WebSocketHumanProvider：operator UI 通道。

#### 必须能力

- submit request
- wait answer
- answer by correlation id
- cancel by syscall id / correlation id
- timeout
- status
- audit
- intervention decision

#### 验收

```bash
AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 PYTHONPATH=. pytest -q tests/test_real_human_channel.py
```

---

### 包 H：storage/memory/context 收口

#### Context

- `compact` 若只是结构压缩，必须文档声明为 structural compact。
- 若做语义压缩，必须接真实 LLM provider。
- `clear/recover` 必须进入 audit。

#### Memory

- export/import/delete 必须权限 + audit。
- FTS 查询必须可解释。
- vector retrieval 只有真实 vector provider 存在时启用。
- 无 vector provider 不得声明 semantic search。

#### Storage

- share registry 必须持久化。
- delete/rollback/share/mount 必须权限 + audit。
- index 可重建，可查询状态。
- retrieve 返回 `retrieval_mode`，例如 `lexical_fts` 或 `semantic_vector`。
- semantic retrieve 只能在真实 embedding/vector provider 可用时返回。

---

### 包 I：app_template 与 e2e smoke

#### 目标

app_template 不只是 bare kernel smoke，而要提供两类 smoke：

1. Bare kernel smoke：context/memory/storage/tool 可真实成功；skill/report 缺 runtime 时稳定失败。
2. Real runtime smoke：启动真实 runtime 后，context/memory/storage/tool/skill/report 成功。

#### 要求

- `agentic_apps/app_template/app.yaml` 权限完整。
- `main.py` 演示 `ctx.kernel.*`。
- 增加 `real_runtime_smoke.py` 或测试入口。
- 文档说明运行命令和依赖。
- 不允许用 mock runtime 让 report.say 成功。

---

### 包 J：测试体系与 CI 分类

#### 测试分类

| 类型 | 说明 |
|---|---|
| unit | SQLite/tempdir/local pure tools，真实本地依赖 |
| integration | kernel queue + manager + provider 闭环 |
| contract | provider config/status/error_code contract |
| real-e2e | 真实 ROS2/LLM/human 依赖，需要 env gate |
| guard | 禁止 mock/simulated surface、禁止伪成功 |

#### 必须新增或强化

```text
tests/test_no_simulated_production_paths.py
tests/test_runtime_real_defaults.py
tests/test_provider_contracts.py
tests/test_access_denied.py
tests/test_audit_trail.py
tests/test_kernel_cancel.py
tests/test_real_integration_contracts.py
tests/test_app_template_real_runtime.py
```

#### CI 要求

默认 CI 跑：

```bash
PYTHONPATH=. pytest -q
```

真实集成 CI 单独跑：

```bash
AGENTIC_VERIFY_REAL_ROS2=1 ...
AGENTIC_VERIFY_REAL_LLM=1 ...
AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 ...
```

如果真实集成依赖未配置，结果必须明确标注未验证，不能通过 mock 成功替代。

---

## 5. 文档交付要求

Codex 需要更新或新增：

```text
docs/kernel_syscalls.md
docs/runtime_real_only.md
docs/provider_contracts.md
docs/access_audit.md
docs/real_integration.md
docs/errors.md
agentic_apps/app_template/README.md
```

文档必须包括：

- 所有 syscall 列表。
- SDK facade 列表。
- 权限表。
- 危险操作表。
- provider 配置矩阵。
- 错误码表。
- status/health 字段。
- real integration 运行命令。
- 不再支持 mock/simulated 运行方式的说明。
- 历史迁移说明。

---

## 6. Git 与本地提交规范

必须直接在当前主分支工作，不创建新分支；本轮**不进行远程推送**；也**不要每完成一个小点就 commit**。Codex 应该先完成整个阶段的所有开发、测试、文档和证据整理，最后只做一次本地 commit。

开始前：

```bash
git status
git branch --show-current
git remote show origin
git config user.email "<developer-email>"
git config user.name "Agentic OS Implementer"
```

确认当前分支是 `main`、`master` 或 `origin/HEAD` 指向的默认主分支。若当前工作区已有用户未提交变更，必须先报告并避免覆盖；不得擅自 reset、rebase、stash 或删除用户修改。

### 6.1 循环内禁止 commit

Loop engineering 仍然按能力面推进，但循环内只记录证据，不提交 commit。每个能力面的完成证据应写入临时执行记录或最终交付摘要，例如：

1. 改动范围。
2. 关键文件。
3. 运行命令。
4. 失败输出。
5. 修复动作。
6. 复测结果。
7. 剩余风险。

推荐能力面推进顺序仍然是：

1. runtime surface：删除生产 mock/simulated surface。
2. provider contract：统一真实 provider/backend contract。
3. access/audit：危险操作权限、intervention、audit 收口。
4. cancel/timeout：长任务生命周期与精确取消。
5. LLM：真实 provider catalog、status、embed、cancel、错误码。
6. ROS2/robot：真实 ROS2 bridge contract 与缺依赖 fail-fast。
7. human：真实 operator channel 与 intervention provider。
8. storage/memory/context/tool：真实持久化、安全边界、检索与状态收尾。
9. tests：unit/integration/contract/real-e2e/guard tests。
10. docs/app_template：文档、app_template smoke、运行手册。

### 6.2 最终单次本地 commit

所有阶段内容完成后，先运行全量验证：

```bash
PYTHONPATH=. pytest -q
git status
git diff --stat
git diff --check
```

确认测试和静态检查结果可接受后，只做一次本地 commit。commit message 使用 Conventional Commits，例如：

```bash
git add .
git commit -m "feat(runtime): complete real-only foundation framework"
```

本轮**不要执行**：

```bash
git push origin HEAD
```

也不要执行任何其他远程推送命令。最终交付只需要报告本地 commit hash、实际运行命令、失败/修复证据、真实集成验证状态和剩余风险。

凭据只能来自环境变量或 credential helper。不得把 API key/token 写入代码、配置、文档、日志、commit message 或测试快照。


## 7. Definition of Done

本轮完成后必须满足：

1. 生产 CLI/API/config/schema 不再暴露 mock/simulated 运行入口。
2. 所有 namespace 都有真实 provider/backend contract。
3. `KernelService.status()` 能展示所有 provider/backend 的真实状态。
4. 所有危险操作经过 access/intervention/audit。
5. 长耗时 syscall 支持 timeout/cancel/status。
6. LLM、ROS2、human 缺依赖时稳定失败；真实配置下有 contract test。
7. context/memory/storage/tool 在本地真实 provider 下端到端成功。
8. app_template 有 bare kernel smoke 和 real runtime smoke。
9. no-simulated guard tests 防止回退。
10. 全量测试通过，真实集成未配置时明确标注未验证。
11. 文档完整列出 syscall、配置、权限、错误码、验证命令。
12. 循环内有完整证据记录，但没有中途 commit。
13. 整个阶段完成后只有一个本地 commit，并报告 commit hash；不进行远程 push。
