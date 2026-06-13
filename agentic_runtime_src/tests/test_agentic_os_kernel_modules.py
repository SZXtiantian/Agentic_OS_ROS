from pathlib import Path

from agentic_os.kernel.device_arbitration import DeviceArbiter
from agentic_os.kernel.memory import MemoryManager
from agentic_os.kernel.model_library import ModelEndpoint, ModelLibrary
from agentic_os.kernel.perception import PerceptionManager
from agentic_os.kernel.scheduler import FIFORequestScheduler, RoundRobinRequestScheduler
from agentic_os.kernel.skill_library import SkillRegistry
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import KernelSyscall, SyscallExecutor
from agentic_os.kernel.tool import ToolManager
from agentic_os.kernel.world_model import WorldModel


def test_kernel_syscall_executor_and_fifo_scheduler_run_memory_request():
    memory = MemoryManager()
    executor = SyscallExecutor()
    executor.register("memory", memory.address_request)
    scheduler = FIFORequestScheduler(executor)

    syscall = KernelSyscall.create(
        agent_name="inspection_agent",
        target="memory",
        operation_type="remember",
        params={"memory_id": "kitchen_last_seen", "content": "clean"},
    )
    scheduler.submit(syscall)
    result = scheduler.run_next()

    assert result is not None
    assert result.success is True
    assert result.response["success"] is True
    assert syscall.status == "done"


def test_round_robin_scheduler_preserves_agent_fairness():
    executor = SyscallExecutor()
    executor.register("echo", lambda syscall: {"agent": syscall.agent_name, "value": syscall.params["value"]})
    scheduler = RoundRobinRequestScheduler(executor)

    scheduler.submit(KernelSyscall.create("agent_a", "echo", "echo", {"value": 1}))
    scheduler.submit(KernelSyscall.create("agent_a", "echo", "echo", {"value": 2}))
    scheduler.submit(KernelSyscall.create("agent_b", "echo", "echo", {"value": 3}))

    results = scheduler.drain()

    assert [result.response["agent"] for result in results] == ["agent_a", "agent_b", "agent_a"]


def test_kernel_storage_context_skill_world_and_device_modules(tmp_path):
    storage = StorageManager(tmp_path / "storage")
    write = storage.write("session/report.json", {"ok": True})
    assert write["success"] is True
    assert storage.read("session/report.json")["success"] is True

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "robot_stop.yaml").write_text("name: robot.stop\ndescription: Stop robot\n", encoding="utf-8")
    skills = SkillRegistry(skill_root)
    assert skills.get("robot.stop").name == "robot.stop"

    places = tmp_path / "places.yaml"
    places.write_text("places:\n  厨房:\n    x: 1.0\n    y: 2.0\n", encoding="utf-8")
    world = WorldModel(places)
    assert world.resolve_place("厨房")["success"] is True

    arbiter = DeviceArbiter()
    assert arbiter.acquire("base", "inspection_agent")["success"] is True
    assert arbiter.acquire("base", "other_agent")["error_code"] == "DEVICE_RESOURCE_BUSY"
    assert arbiter.release("base", "inspection_agent")["success"] is True


def test_kernel_tool_model_and_perception_modules():
    tools = ToolManager()
    tools.register("math.add", lambda args: args["a"] + args["b"])
    syscall = KernelSyscall.create(
        "inspection_agent",
        "tool",
        "math.add",
        {"name": "math.add", "args": {"a": 2, "b": 3}},
    )
    assert tools.address_request(syscall)["result"] == 5
    forbidden = KernelSyscall.create("inspection_agent", "tool", "robot.navigate_to", {"name": "robot.navigate_to"})
    assert tools.address_request(forbidden)["error_code"] == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"

    models = ModelLibrary([ModelEndpoint(name="mock-vla", provider="mock", capabilities=("chat", "vla"))])
    assert models.route("vla")["endpoint"]["name"] == "mock-vla"

    perception = PerceptionManager()
    normalized = perception.normalize_inspection("厨房", {"objects": ["table"], "anomalies": []})
    assert normalized["success"] is True
    assert perception.latest("inspection:厨房")["success"] is True


def test_installed_kernel_import_surface_exists_when_opt_agentic_is_present():
    root = Path("/opt/agentic")
    if not root.exists():
        return
    assert (root / "agentic_os" / "kernel" / "system_call" / "executor.py").is_file()
    assert (root / "agentic_os" / "kernel" / "memory" / "manager.py").is_file()
