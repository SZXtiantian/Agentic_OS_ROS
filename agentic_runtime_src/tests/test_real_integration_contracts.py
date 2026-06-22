from __future__ import annotations

import asyncio
import os
import shutil

import pytest

from agentic_os.kernel.llm_core import LLMConfig, OpenAICompatibleProvider
from agentic_os.kernel.system_call import LLMQuery
from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.ros_bridge_client import Ros2CliBridgeClient
from agentic_runtime.types import new_id


def _require_enabled(flag_name: str, skip_code: str) -> None:
    if os.environ.get(flag_name) != "1":
        pytest.skip(f"{skip_code}: set {flag_name}=1 to verify this real integration; no simulated success was used")


@pytest.mark.integration
@pytest.mark.ros2
def test_real_ros2_bridge_contract_is_opt_in_and_never_simulated():
    _require_enabled("AGENTIC_VERIFY_REAL_ROS2", "UNVERIFIED_REAL_ROS2_BRIDGE")
    if shutil.which("ros2") is None:
        pytest.fail("UNVERIFIED_REAL_ROS2_BRIDGE: ros2 executable is not available")

    result = asyncio.run(Ros2CliBridgeClient().get_robot_state())

    assert result["success"] is True, (
        "real ROS2 bridge contract failed without fallback: "
        f"error_code={result.get('error_code')} reason={result.get('reason')}"
    )


@pytest.mark.integration
def test_real_llm_provider_contract_is_opt_in_and_never_simulated():
    _require_enabled("AGENTIC_VERIFY_REAL_LLM", "UNVERIFIED_REAL_LLM_PROVIDER")
    missing = [
        name
        for name in ("AGENTIC_REAL_LLM_BASE_URL", "AGENTIC_REAL_LLM_API_KEY", "AGENTIC_REAL_LLM_MODEL")
        if not os.environ.get(name)
    ]
    if missing:
        pytest.fail(f"UNVERIFIED_REAL_LLM_PROVIDER: missing required env vars: {', '.join(missing)}")

    provider = OpenAICompatibleProvider(
        LLMConfig(
            name="real-openai-compatible",
            backend="openai_compatible",
            hostname=os.environ["AGENTIC_REAL_LLM_BASE_URL"],
            api_key_env="AGENTIC_REAL_LLM_API_KEY",
            model=os.environ["AGENTIC_REAL_LLM_MODEL"],
            timeout_s=float(os.environ.get("AGENTIC_REAL_LLM_TIMEOUT_S", "30")),
        )
    )
    response = provider.complete(LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "Reply with ok."}]))

    assert response.success is True, (
        "real LLM provider contract failed without fallback: "
        f"error_code={response.error_code} metadata={response.metadata}"
    )


@pytest.mark.integration
def test_real_human_queue_contract_is_opt_in_and_never_auto_answers(tmp_path):
    _require_enabled("AGENTIC_VERIFY_REAL_HUMAN_QUEUE", "UNVERIFIED_REAL_HUMAN_QUEUE")
    root = os.environ.get("AGENTIC_REAL_HUMAN_QUEUE_ROOT") or str(tmp_path / "human")
    correlation_id = os.environ.get("AGENTIC_REAL_HUMAN_CORRELATION_ID") or new_id("real_human")
    timeout_s = float(os.environ.get("AGENTIC_REAL_HUMAN_TIMEOUT_S", "30"))
    channel = FileHumanQueueChannel(root, poll_interval_s=0.1)

    async def run():
        return await channel.ask(
            question="Real integration verification: reply in the configured human queue.",
            timeout_s=timeout_s,
            app_id="real_integration_contract",
            session_id="real_human_contract",
            correlation_id=correlation_id,
        )

    result = asyncio.run(run())

    assert result["success"] is True, (
        "real human queue contract failed without fallback: "
        f"error_code={result.get('error_code')} correlation_id={correlation_id} request_path={channel.paths.requests}"
    )
