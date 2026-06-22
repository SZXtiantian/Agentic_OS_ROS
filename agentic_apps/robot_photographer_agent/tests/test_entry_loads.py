import importlib.util
import sys
from pathlib import Path

RUNTIME_SRC = Path(__file__).resolve().parents[3] / "agentic_runtime_src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client.mock_client import MockRosBridgeClient
from agentic_runtime.server import RuntimeServer


APP_DIR = Path(__file__).parents[1]


def test_entry_module_loads_robot_photographer_agent():
    spec = importlib.util.spec_from_file_location("robot_photographer_agent.entry", APP_DIR / "entry.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert hasattr(module, "RobotPhotographerAgent")


def test_run_smoke_returns_validation_result_for_motion_without_permission():
    spec = importlib.util.spec_from_file_location("robot_photographer_agent.entry", APP_DIR / "entry.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    config = RuntimeConfig.load()
    server = RuntimeServer.create(mock=True, bridge_client=MockRosBridgeClient(config.repo_root))
    agent = module.RobotPhotographerAgent(runtime=server, mock=True)
    result = agent.run({"text": "把相机抬起来再拍一张", "mock": True})
    assert result["success"] is False
    assert result["error_code"] == "ARM_MOTION_DISABLED"
