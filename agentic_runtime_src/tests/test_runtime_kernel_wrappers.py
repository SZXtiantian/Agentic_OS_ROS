import asyncio

from agentic_os.kernel.context import ContextManager as KernelContextManager
from agentic_os.kernel.device_arbitration import DeviceArbiter
from agentic_os.kernel.memory import MemoryManager as KernelMemoryManager
from agentic_os.kernel.scheduler import FIFORequestScheduler
from agentic_os.kernel.skill_library import SkillRegistry as KernelSkillRegistry
from agentic_os.kernel.storage import StorageManager as KernelStorageManager
from agentic_os.kernel.system_call import KernelSyscallStatus
from agentic_os.kernel.tool import ToolManager as KernelToolManager

from agentic_runtime.context_manager import ContextManager
from agentic_runtime.memory import create_memory_manager
from agentic_runtime.ros_bridge_client.mock_client import MockRosBridgeClient
from agentic_runtime.scheduler import SingleRobotScheduler
from agentic_runtime.skill_executor.resource_manager import ResourceManager
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.storage import StorageManager
from agentic_runtime.syscall import AgenticSyscall, SyscallStatus
from agentic_runtime.tool_manager import ToolCall, ToolManager


def test_runtime_memory_manager_is_kernel_backed(tmp_path):
    manager = create_memory_manager("sqlite", tmp_path / "memory.sqlite3")

    assert isinstance(manager.kernel, KernelMemoryManager)

    manager.remember("inspection_agent", "sess_1", "last", {"summary": "厨房 ok"})
    assert manager.recall("inspection_agent", "last") == {"summary": "厨房 ok"}
    assert manager.search("inspection_agent", "厨房")[0]["key"] == "last"


def test_runtime_storage_and_context_are_kernel_backed(tmp_path):
    storage = StorageManager(tmp_path / "storage")
    context = ContextManager(tmp_path / "context")

    assert isinstance(storage.kernel, KernelStorageManager)
    assert isinstance(context.kernel, KernelContextManager)

    artifact = storage.write_artifact("sess_1", "inspection.json", {"ok": True})
    assert artifact.path.endswith("sess_1/inspection.json")

    context.snapshot("sess_1", "inspection_agent", task={"place": "厨房"})
    recovered = context.recover("sess_1")
    assert recovered is not None
    assert recovered.task == {"place": "厨房"}


def test_runtime_tool_and_resource_managers_are_kernel_backed():
    tools = ToolManager()
    resources = ResourceManager()

    assert isinstance(tools.kernel, KernelToolManager)
    assert isinstance(resources.kernel, DeviceArbiter)

    assert tools.call(ToolCall(name="echo", args={"message": "hi"})).data == {"message": "hi"}
    lease = resources.acquire("base", "sess_1", "call_1")
    assert lease.resource == "base"
    resources.release("base", "sess_1", "call_1")
    assert resources.snapshot() == {}


def test_runtime_scheduler_uses_kernel_fifo_admission():
    class Runner:
        async def run_app(self, app_id, **kwargs):
            return {"app_id": app_id, "kwargs": kwargs, "result": {"success": True}}

    scheduler = SingleRobotScheduler(Runner())

    assert isinstance(scheduler.kernel_scheduler, FIFORequestScheduler)
    result = asyncio.run(scheduler.run_app("inspection_agent", place="厨房", mock=True))

    assert result["result"]["success"] is True
    assert scheduler.status()["last_kernel_syscall_id"].startswith("ksc_")


def test_runtime_skill_registry_and_syscall_status_use_kernel_contracts(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "echo.yaml").write_text(
        """
name: tool.echo
version: "0.1"
input_schema:
  type: object
output_schema:
  type: object
permission_requirements: []
resource_requirements:
  locks: []
backend:
  type: runtime_internal
""".strip(),
        encoding="utf-8",
    )
    registry = SkillRegistry(skill_root).load()

    assert isinstance(registry.kernel, KernelSkillRegistry)
    assert registry.get_skill("tool.echo").name == "tool.echo"
    assert SyscallStatus.DONE == KernelSyscallStatus.DONE
    syscall = AgenticSyscall.create("app", "sess", "memory.remember", {"key": "x"})
    kernel_syscall = syscall.to_kernel_syscall()
    assert kernel_syscall.operation_type == "memory.remember"


def test_mock_bridge_uses_kernel_world_model(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "places.yaml").write_text(
        "places:\n  厨房:\n    id: kitchen\n    frame_id: map\n    pose: {x: 1, y: 2, yaw: 0}\n    allowed: true\n",
        encoding="utf-8",
    )
    (configs / "safety.yaml").write_text("safety:\n  forbidden_zones: []\n", encoding="utf-8")
    bridge = MockRosBridgeClient(tmp_path)

    assert bridge.world_model.resolve_place("厨房")["success"] is True
    resolved = asyncio.run(bridge.resolve_place("厨房"))
    assert resolved["place"]["id"] == "kitchen"
