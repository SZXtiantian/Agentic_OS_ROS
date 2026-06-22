from agentic_os.kernel.hooks import KernelQueueName
from agentic_os.kernel.system_call import (
    ContextQuery,
    ContextSyscall,
    LLMQuery,
    LLMSyscall,
    MemoryQuery,
    MemorySyscall,
    RobotCapabilityQuery,
    RobotCapabilitySyscall,
    SkillQuery,
    SkillSyscall,
    StorageQuery,
    StorageSyscall,
    ToolQuery,
    ToolSyscall,
    create_syscall,
)


def test_factory_creates_llm_syscall():
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}]),
    )

    assert isinstance(syscall, LLMSyscall)
    assert syscall.target == KernelQueueName.LLM
    assert syscall.queue_name == KernelQueueName.LLM


def test_factory_creates_memory_storage_and_tool_syscalls():
    memory = create_syscall("agent_a", MemoryQuery(operation_type="remember", params={"key": "x"}))
    storage = create_syscall("agent_a", StorageQuery(operation_type="sto_write", params={"path": "x"}))
    tool = create_syscall("agent_a", ToolQuery(operation_type="call_tool", tool_calls=[]))

    assert isinstance(memory, MemorySyscall)
    assert isinstance(storage, StorageSyscall)
    assert isinstance(tool, ToolSyscall)
    assert memory.queue_name == KernelQueueName.MEMORY
    assert storage.queue_name == KernelQueueName.STORAGE
    assert tool.queue_name == KernelQueueName.TOOL


def test_factory_creates_context_and_skill_syscalls():
    context = create_syscall("agent_a", ContextQuery(operation_type="ctx_put", params={"key": "x"}))
    skill = create_syscall("agent_a", SkillQuery(operation_type="skill_call", skill_name="report.say"))

    assert isinstance(context, ContextSyscall)
    assert isinstance(skill, SkillSyscall)
    assert context.queue_name == KernelQueueName.CONTEXT
    assert skill.queue_name == KernelQueueName.SKILL


def test_factory_creates_robot_motion_syscall_lane():
    syscall = create_syscall(
        "agent_a",
        RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to"),
    )

    assert isinstance(syscall, RobotCapabilitySyscall)
    assert syscall.queue_name == KernelQueueName.ROBOT_MOTION
    assert syscall.target == KernelQueueName.ROBOT_MOTION


def test_factory_routes_robot_sensor_and_human_lanes():
    sensor = create_syscall(
        "agent_a",
        RobotCapabilityQuery(operation_type="execute_skill", skill_name="perception.capture_photo"),
    )
    human = create_syscall(
        "agent_a",
        RobotCapabilityQuery(operation_type="execute_skill", skill_name="human.ask"),
    )

    assert sensor.queue_name == KernelQueueName.ROBOT_SENSOR
    assert human.queue_name == KernelQueueName.HUMAN
