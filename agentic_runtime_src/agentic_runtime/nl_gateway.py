from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agentic_runtime.config import find_repo_root
from agentic_runtime.dispatcher import DispatcherAgent
from agentic_runtime.server import RuntimeServer


BRIDGE_SCRIPT = Path(
    os.environ.get(
        "AGENTIC_ROBOT_SKILLS_SCRIPT",
        os.environ.get("AGENTIC_ROBOT_BRIDGE_SCRIPT", find_repo_root() / "scripts" / "run_robot_skills.sh"),
    )
)
BRIDGE_LOG = Path("/tmp/agentic_nl_gateway_bridge.log")
REQUIRED_BRIDGE_SERVICES = {
    "/agentic/robot/get_state",
    "/agentic/perception/capture_photo",
    "/agentic/safety/check",
    "/agentic/robot/stop",
}
BRIDGE_PROCESS_PATTERN = "ros2 launch agentic_capability_bridge robot_test.launch.py"
EXIT_WORDS = {"退出", "exit", "quit", "q", "bye"}


@dataclass(frozen=True)
class GatewayFlags:
    real: bool = True
    json: bool = False
    allow_arm_motion: bool = False
    assume_yes: bool = False
    show_plan: bool = False
    dry_run: bool = False
    no_llm: bool = False
    require_llm: bool = False
    forced_app_id: str | None = None
    tasks_limit: int = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic")
    parser.add_argument("--real", action="store_true", default=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-arm-motion", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--show-plan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--app", dest="forced_app_id")
    parser.add_argument("--tasks-limit", type=int, default=20)
    parser.add_argument("text", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    flags = _flags_from_args(args)
    text = " ".join(args.text).strip()
    if text:
        return asyncio.run(run_once(text, flags))
    return asyncio.run(run_interactive(flags))


async def run_once(user_text: str, flags: GatewayFlags) -> int:
    if user_text.strip() in EXIT_WORDS:
        return 0
    result = await dispatch_text(user_text, flags)
    print_result(result, as_json=flags.json)
    return 0 if bool(result.get("success")) else 1


async def dispatch_text(user_text: str, flags: GatewayFlags) -> dict[str, Any]:
    if flags.real and _likely_needs_real_bridge(user_text, flags) and not _ensure_real_bridge_ready(flags):
        return {
            "success": False,
            "status": "failed",
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "message": "AgenticOS real bridge services are unavailable",
        }
    with _operator_intervention_env(flags):
        server = RuntimeServer.create()
        dispatcher = DispatcherAgent(server)
        if flags.json:
            with contextlib.redirect_stdout(io.StringIO()):
                return await dispatcher.arun(user_text, flags)
        return await dispatcher.arun(user_text, flags)


async def run_interactive(flags: GatewayFlags) -> int:
    print("AgenticOS ready. 输入 `帮助` 查看命令，输入 `退出` 结束。")
    while True:
        try:
            text = input("agentic> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 130
        if not text:
            continue
        if text in EXIT_WORDS:
            return 0
        result = await dispatch_text(text, flags)
        print_result(result, as_json=flags.json)
        if result.get("error_code") == "DISPATCH_CONFIRMATION_REQUIRED":
            answer = input("计划需要受控机械臂动作，是否执行？ yes/no\nagentic> ").strip().lower()
            if answer in {"yes", "y", "是"}:
                confirmed = replace(flags, assume_yes=True)
                confirmed_result = await dispatch_text(text, confirmed)
                print_result(confirmed_result, as_json=flags.json)


def print_result(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"task_id: {result.get('task_id', '')}")
    print(f"status: {result.get('status', '')}")
    print(f"success: {result.get('success')}")
    if result.get("selected_app_id"):
        print(f"selected_app: {result.get('selected_app_id')}")
    if result.get("error_code"):
        print(f"error_code: {result.get('error_code')}")
        print(f"message: {result.get('message', '')}")
    summary = dict(result.get("result_summary") or {})
    if summary.get("summary"):
        print(f"summary: {summary.get('summary')}")
    for path in summary.get("app_output_paths", []):
        print(f"app_output: {path}")
    for path in summary.get("raw_evidence_paths", []):
        print(f"raw_evidence: {path}")
    if result.get("task_log_path"):
        print(f"task_log: {result.get('task_log_path')}")


def _flags_from_args(args: argparse.Namespace) -> GatewayFlags:
    return GatewayFlags(
        real=True,
        json=bool(args.json),
        allow_arm_motion=bool(args.allow_arm_motion),
        assume_yes=bool(args.yes),
        show_plan=bool(args.show_plan),
        dry_run=bool(args.dry_run),
        no_llm=bool(args.no_llm),
        require_llm=bool(args.require_llm),
        forced_app_id=args.forced_app_id,
        tasks_limit=int(args.tasks_limit),
    )


@contextlib.contextmanager
def _operator_intervention_env(flags: GatewayFlags):
    keys = {
        "AGENTIC_OPERATOR_INTERVENTION_APPROVED",
        "AGENTIC_OPERATOR_INTERVENTION_SOURCE",
        "AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION",
    }
    previous = {key: os.environ.get(key) for key in keys}
    try:
        if flags.assume_yes:
            os.environ["AGENTIC_OPERATOR_INTERVENTION_APPROVED"] = "1"
            os.environ["AGENTIC_OPERATOR_INTERVENTION_SOURCE"] = "cli_yes_flag"
        if flags.allow_arm_motion:
            os.environ["AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION"] = "1"
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _likely_needs_real_bridge(user_text: str, flags: GatewayFlags) -> bool:
    if flags.dry_run:
        return False
    text = user_text.lower()
    if any(token in user_text for token in ("最近任务", "上一个任务", "帮助")):
        return False
    if any(token in text for token in ("tasks", "last task", "help")):
        return False
    return True


def _ensure_real_bridge_ready(flags: GatewayFlags) -> bool:
    if _bridge_services_ready(timeout_s=8):
        return True
    if not BRIDGE_SCRIPT.exists():
        return False
    if not _external_bridge_running():
        BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BRIDGE_LOG.open("ab") as log:
            subprocess.Popen([str(BRIDGE_SCRIPT)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        if not flags.json:
            print(f"AgenticOS bridge 未运行，已自动启动，日志: {BRIDGE_LOG}")
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        if _bridge_services_ready(timeout_s=3):
            return True
        time.sleep(0.5)
    return False


def _external_bridge_running() -> bool:
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


def _bridge_services_ready(timeout_s: int) -> bool:
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
        services = {_service_name_from_line(line) for line in result.stdout.splitlines() if line.strip()}
        if REQUIRED_BRIDGE_SERVICES.issubset(services):
            return True
    return False


def _service_name_from_line(line: str) -> str:
    return line.split("[", 1)[0].strip()


if __name__ == "__main__":
    raise SystemExit(main())
