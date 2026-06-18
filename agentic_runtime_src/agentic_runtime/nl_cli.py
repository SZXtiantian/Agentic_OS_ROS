from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_runtime.config import find_repo_root
from agentic_runtime.server import RuntimeServer


HELP_TEXT = """AgenticOS natural language CLI

Examples:
  看一下工作区
  拍一张 workspace 的照片
  查看状态
  最近会话
  最近审计
  停止机器人
  退出

Arm motion is disabled unless you start chat with --allow-arm-motion or set
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1.

For real robot commands, this CLI starts the AgenticOS ROS bridge automatically
when the bridge services are not already running.
"""

BRIDGE_SCRIPT = Path(os.environ.get("AGENTIC_ROBOT_BRIDGE_SCRIPT", find_repo_root() / "scripts" / "run_robot_bridge.sh"))
BRIDGE_LOG = Path("/tmp/agentic_chat_bridge.log")
REQUIRED_BRIDGE_SERVICES = {
    "/agentic/robot/get_state",
    "/agentic/arm/get_state",
    "/agentic/perception/observe",
    "/agentic/safety/check",
    "/agentic/robot/stop",
}


@dataclass(frozen=True)
class NaturalLanguageIntent:
    action: str
    place: str = "workspace"
    move_arm: bool = False
    raw: str = ""


def parse_natural_language(text: str) -> NaturalLanguageIntent:
    raw = text.strip()
    normalized = raw.lower()
    compact = re.sub(r"\s+", "", normalized)
    if not raw:
        return NaturalLanguageIntent("noop", raw=raw)
    if compact in {"q", "quit", "exit", "bye", "退出", "结束", "再见"}:
        return NaturalLanguageIntent("exit", raw=raw)
    if any(token in normalized for token in ("help", "?")) or any(token in raw for token in ("帮助", "怎么用")):
        return NaturalLanguageIntent("help", raw=raw)
    if any(token in normalized for token in ("status", "state")) or any(token in raw for token in ("状态", "现在情况")):
        return NaturalLanguageIntent("status", raw=raw)
    if any(token in normalized for token in ("session", "sessions")) or any(token in raw for token in ("会话", "任务记录")):
        return NaturalLanguageIntent("sessions", raw=raw)
    if "audit" in normalized or any(token in raw for token in ("审计", "日志")):
        return NaturalLanguageIntent("audit", raw=raw)
    if any(token in normalized for token in ("stop", "cancel")) or any(token in raw for token in ("停止", "急停", "取消")):
        return NaturalLanguageIntent("stop", raw=raw)

    move_arm = any(token in normalized for token in ("camera_up", "arm_home", "move arm", "raise camera")) or any(
        token in raw for token in ("抬起", "机械臂", "动一下", "回到初始")
    )
    inspect = any(token in normalized for token in ("inspect", "observe", "camera", "photo", "picture", "image", "look")) or any(
        token in raw for token in ("检查", "观察", "相机", "拍照", "照片", "图像", "图片", "看一下", "看看")
    )
    if inspect or move_arm:
        return NaturalLanguageIntent("camera_arm_inspection", place=_extract_place(raw), move_arm=move_arm, raw=raw)
    return NaturalLanguageIntent("unknown", raw=raw)


def _extract_place(text: str) -> str:
    normalized = text.lower()
    match = re.search(r"(?:place|target)\s*[:=]\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)", text)
    if match:
        return match.group(1)
    if "workspace" in normalized or "工作区" in text or "桌面" in text:
        return "workspace"
    for place in ("厨房", "客厅", "门口", "充电区"):
        if place in text:
            return place
    return "workspace"


class AgenticNaturalLanguageCLI:
    def __init__(self, *, real: bool = True, json_output: bool = False, allow_arm_motion: bool = False) -> None:
        self.real = real
        self.json_output = json_output
        self.allow_arm_motion = allow_arm_motion or os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION") == "1"
        self._bridge_process: subprocess.Popen | None = None

    async def run_text(self, text: str) -> int:
        intent = parse_natural_language(text)
        if intent.action == "noop":
            return 0
        if intent.action == "exit":
            return 130
        if intent.action == "help":
            print(HELP_TEXT)
            return 0
        if intent.action == "unknown":
            print("我还不认识这条指令。输入 `帮助` 可以看当前支持的自然语言命令。")
            return 1
        if intent.action == "status":
            self._print_status()
            return 0
        if intent.action == "sessions":
            self._print_sessions()
            return 0
        if intent.action == "audit":
            self._print_audit()
            return 0
        if intent.action == "stop":
            return await self._stop_robot()
        if intent.action == "camera_arm_inspection":
            return await self._run_camera_arm_inspection(intent)
        print(f"unsupported intent: {intent.action}")
        return 1

    async def _run_camera_arm_inspection(self, intent: NaturalLanguageIntent) -> int:
        if not self._ensure_real_bridge_ready():
            self._print_bridge_unavailable()
            return 1
        previous = os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION")
        motion_requested = bool(intent.move_arm)
        motion_enabled = motion_requested and self.allow_arm_motion
        if motion_requested and not motion_enabled:
            print("机械臂动作已被安全策略拦下；本次按只读相机观察执行。")
        if motion_enabled:
            os.environ["AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION"] = "1"
        else:
            os.environ.pop("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", None)
        try:
            server = RuntimeServer.create(mock=not self.real)
            result = await server.scheduler.run_app(
                "camera_arm_inspection_agent",
                place=intent.place,
                mock=not self.real,
            )
        finally:
            if previous is None:
                os.environ.pop("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", None)
            else:
                os.environ["AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION"] = previous
        self._print_app_result(result)
        return 0 if bool(result.get("result", {}).get("success")) else 1

    async def _stop_robot(self) -> int:
        if not self._ensure_real_bridge_ready():
            self._print_bridge_unavailable()
            return 1
        server = RuntimeServer.create(mock=not self.real)
        result = await server.executor.dispatcher.bridge_client.stop_robot("operator_requested_from_agentic_chat")
        if self.json_output:
            print_json(result)
        else:
            print("stop result:")
            print_json(result)
        return 0 if bool(result.get("success", False)) else 1

    def _print_status(self) -> None:
        server = RuntimeServer.create(mock=not self.real)
        data = server.monitor.status([skill.name for skill in server.registry.list_skills()], ros_bridge=server.config.ros_bridge_mode)
        data["scheduler"] = server.scheduler.status()
        if self.json_output:
            print_json(data)
            return
        print(f"ros_bridge: {data['ros_bridge']}")
        print(f"scheduler: {data['scheduler']['policy']}")
        print("skills:")
        for item in data["skills"]:
            print(f"  - {item['name']}: {item['status']}")
        recent = data.get("recent_syscalls", [])
        if recent:
            print("recent:")
            for record in recent[-5:]:
                print(f"  - {record.get('skill_name')}: {record.get('status')} {record.get('error_code')}")

    def _print_sessions(self) -> None:
        server = RuntimeServer.create(mock=not self.real)
        sessions = [record.to_dict() for record in server.session_manager.list_sessions(limit=10)]
        if self.json_output:
            print_json(sessions)
            return
        for record in sessions:
            print(f"{record['session_id']} {record['app_id']} {record['status']}")

    def _print_audit(self) -> None:
        server = RuntimeServer.create(mock=not self.real)
        records = server.audit_logger.recent(limit=20)
        if self.json_output:
            print_json(records)
            return
        for record in records:
            print(f"{record.get('audit_id')} {record.get('skill_name')} {record.get('status')} {record.get('error_code')}")

    def _print_app_result(self, result: dict[str, Any]) -> None:
        if self.json_output:
            print_json(result)
            return
        app_result = dict(result.get("result") or {})
        observation = dict(app_result.get("observation") or {})
        arm_state = dict(app_result.get("arm_state") or {})
        print(f"session_id: {result.get('session_id')}")
        print(f"status: {result.get('status')}")
        print(f"success: {app_result.get('success')}")
        if not app_result.get("success"):
            print(f"error_code: {app_result.get('error_code', '')}")
            if app_result.get("reason"):
                print(f"reason: {app_result.get('reason')}")
            if app_result.get("stop_result"):
                print("stop_result:")
                print_json(app_result.get("stop_result"))
        if observation:
            print(f"observation: {observation.get('summary')}")
            if observation.get("evidence_path"):
                print(f"evidence: {observation.get('evidence_path')}")
        if arm_state:
            print(f"arm: {arm_state.get('readiness')} stop_available={arm_state.get('stop_available')}")
        if app_result.get("motion_enabled"):
            print(f"arm_action: {app_result.get('arm_action')}")
            print(f"gripper_action: {app_result.get('gripper_action')}")

    def _ensure_real_bridge_ready(self) -> bool:
        if not self.real:
            return True
        if self._bridge_services_ready(timeout_s=5):
            return True
        if not BRIDGE_SCRIPT.exists():
            return False
        if self._bridge_process is None or self._bridge_process.poll() is not None:
            BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            log = BRIDGE_LOG.open("ab")
            self._bridge_process = subprocess.Popen(
                [str(BRIDGE_SCRIPT)],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            if not self.json_output:
                print(f"AgenticOS bridge 未运行，已自动启动，日志: {BRIDGE_LOG}")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self._bridge_services_ready(timeout_s=3):
                return True
            time.sleep(0.5)
        return False

    def _bridge_services_ready(self, timeout_s: int = 5) -> bool:
        try:
            result = subprocess.run(
                ["ros2", "service", "list", "--no-daemon"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False
        services = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        return REQUIRED_BRIDGE_SERVICES.issubset(services)

    def _print_bridge_unavailable(self) -> None:
        data = {
            "success": False,
            "error_code": "AGENTIC_BRIDGE_UNAVAILABLE",
            "reason": f"AgenticOS bridge services did not become ready; see {BRIDGE_LOG}",
        }
        if self.json_output:
            print_json(data)
            return
        print("AgenticOS bridge 没有 ready，无法执行真实机器人命令。")
        print(f"日志: {BRIDGE_LOG}")

    def close(self) -> None:
        if self._bridge_process is None or self._bridge_process.poll() is not None:
            return
        try:
            os.killpg(self._bridge_process.pid, signal.SIGINT)
            self._bridge_process.wait(timeout=5)
        except Exception:
            try:
                os.killpg(self._bridge_process.pid, signal.SIGTERM)
            except Exception:
                pass


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


async def interactive(args: argparse.Namespace) -> int:
    cli = AgenticNaturalLanguageCLI(real=args.real, json_output=args.json, allow_arm_motion=args.allow_arm_motion)
    try:
        if args.command:
            return await cli.run_text(" ".join(args.command))
        print("AgenticOS chat ready. 输入 `帮助` 查看命令，输入 `退出` 结束。")
        while True:
            try:
                text = input("agentic> ")
            except EOFError:
                print()
                return 0
            rc = await cli.run_text(text)
            if rc == 130:
                return 0
    finally:
        cli.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic chat")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--real", action="store_true", dest="real", default=True)
    mode.add_argument("--mock", action="store_false", dest="real")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-arm-motion", action="store_true")
    parser.add_argument("command", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(interactive(args))


if __name__ == "__main__":
    raise SystemExit(main())
