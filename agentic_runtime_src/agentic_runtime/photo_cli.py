from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agentic_runtime.config import find_repo_root
from agentic_runtime.server import RuntimeServer


_RUNTIME_SRC = find_repo_root()
APP_DIR = Path(os.environ.get("AGENTIC_APP_ROOT", _RUNTIME_SRC.parent / "agentic_apps")) / "robot_photographer_agent"
BRIDGE_SCRIPT = Path(os.environ.get("AGENTIC_ROBOT_BRIDGE_SCRIPT", _RUNTIME_SRC / "scripts" / "run_robot_bridge.sh"))
BRIDGE_LOG = Path("/tmp/agentic_photo_bridge.log")
REQUIRED_BRIDGE_SERVICES = {
    "/agentic/robot/get_state",
    "/agentic/arm/get_state",
    "/agentic/perception/capture_photo",
    "/agentic/safety/check",
    "/agentic/robot/stop",
}
BRIDGE_PROCESS_PATTERN = "ros2 launch agentic_capability_bridge robot_test.launch.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic photo")
    parser.add_argument("--real", action="store_true", default=False)
    parser.add_argument("--mock", action="store_true", default=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-arm-motion", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("command", nargs="*")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    real = bool(args.real and not args.mock)
    cli = RobotPhotoCLI(real=real, json_output=args.json, allow_arm_motion=args.allow_arm_motion, assume_yes=args.yes)
    text = " ".join(args.command).strip()
    if text:
        return asyncio.run(cli.run_text(text))
    return asyncio.run(cli.interactive())


class RobotPhotoCLI:
    def __init__(self, *, real: bool, json_output: bool, allow_arm_motion: bool, assume_yes: bool) -> None:
        self.real = real
        self.json_output = json_output
        self.allow_arm_motion = allow_arm_motion or os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION") == "1"
        self.assume_yes = assume_yes
        self._bridge_process: subprocess.Popen | None = None

    async def interactive(self) -> int:
        print("Robot Photographer ready. 输入 `帮助` 查看命令，输入 `退出` 结束。")
        while True:
            try:
                text = input("photo> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 130
            if text in {"退出", "exit", "quit", "q"}:
                return 0
            if text in {"帮助", "help", "?"}:
                self._print_help()
                continue
            code = await self.run_text(text)
            if code == 2:
                answer = input("计划需要机械臂动作，是否执行？ yes/no\nphoto> ").strip().lower()
                if answer in {"yes", "y", "是"}:
                    previous = self.assume_yes
                    self.assume_yes = True
                    try:
                        code = await self.run_text(text)
                    finally:
                        self.assume_yes = previous
            if code not in {0, 2}:
                return code

    async def run_text(self, text: str) -> int:
        if not text:
            return 0
        if self.real and not self._ensure_real_bridge_ready():
            result = {"success": False, "error_code": "AGENTIC_BRIDGE_UNAVAILABLE", "reason": "AgenticOS real bridge services are unavailable"}
            self._print_result(result)
            return 1
        task_input = {
            "text": text,
            "allow_arm_motion": self.allow_arm_motion,
            "assume_yes": self.assume_yes,
            "mock": not self.real,
        }
        server = RuntimeServer.create(mock=not self.real)
        agent = self._load_agent(runtime=server, mock=not self.real)
        result = await agent.arun(task_input)
        self._print_result(result)
        app_result = dict(result.get("result") or result)
        if app_result.get("error_code") == "ARM_CONFIRMATION_REQUIRED":
            return 2
        return 0 if bool(app_result.get("success")) else 1

    def _load_agent(self, runtime: RuntimeServer, mock: bool):
        if str(APP_DIR) not in sys.path:
            sys.path.insert(0, str(APP_DIR))
        entry = APP_DIR / "entry.py"
        spec = importlib.util.spec_from_file_location("robot_photographer_agent.entry", entry)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load Robot Photographer entry: {entry}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.RobotPhotographerAgent(runtime=runtime, mock=mock)

    def _ensure_real_bridge_ready(self) -> bool:
        if self._bridge_services_ready(timeout_s=12):
            return True
        bridge_running = self._managed_bridge_running() or self._external_bridge_running()
        if bridge_running and not self.json_output:
            print("AgenticOS bridge appears to be running; waiting for services.")
        if not BRIDGE_SCRIPT.exists():
            return False
        if not bridge_running:
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
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if self._bridge_services_ready(timeout_s=3):
                return True
            time.sleep(0.5)
        return False

    def _managed_bridge_running(self) -> bool:
        return self._bridge_process is not None and self._bridge_process.poll() is None

    def _external_bridge_running(self) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", BRIDGE_PROCESS_PATTERN],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and bool(result.stdout.strip())

    def _bridge_services_ready(self, timeout_s: int) -> bool:
        commands = (
            ["ros2", "service", "list", "-t", "--no-daemon"],
            ["ros2", "service", "list", "-t"],
            ["ros2", "service", "list", "--no-daemon"],
            ["ros2", "service", "list"],
        )
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout_s,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if result.returncode != 0:
                continue
            services = {self._service_name_from_line(line) for line in result.stdout.splitlines() if line.strip()}
            if REQUIRED_BRIDGE_SERVICES.issubset(services):
                return True
        return False

    def _service_name_from_line(self, line: str) -> str:
        return line.split("[", 1)[0].strip()

    def _print_result(self, result: dict[str, Any]) -> None:
        if self.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return
        app_result = dict(result.get("result") or result)
        if "session_id" in result:
            print(f"session_id: {result.get('session_id')}")
            print(f"status: {result.get('status')}")
        print(f"success: {app_result.get('success')}")
        if app_result.get("error_code"):
            print(f"error_code: {app_result.get('error_code')}")
            print(f"reason: {app_result.get('reason', '')}")
        for step in app_result.get("steps", []):
            if step.get("type") == "capture_photo" and step.get("success"):
                print(f"图片: {step.get('image_path', '')}")
                print(f"元数据: {step.get('metadata_path', '')}")
            elif step.get("type") == "arm_named_action":
                print(f"arm action: {step.get('name')} success={step.get('success')}")
            elif step.get("type") == "recent_photos":
                for photo in step.get("photos", []):
                    print(photo.get("image_path", ""))
            elif step.get("type") == "status":
                print(json.dumps(step, ensure_ascii=False, indent=2, sort_keys=True))

    def _print_help(self) -> None:
        print(
            "Robot Photographer commands:\n"
            "  拍一张照片\n"
            "  把相机抬起来再拍一张\n"
            "  回到初始位\n"
            "  连续拍三张\n"
            "  查看最近照片\n"
            "  状态\n"
            "  停止\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
