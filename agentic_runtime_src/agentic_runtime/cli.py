from __future__ import annotations

import argparse
import asyncio
import json

from agentic_runtime.hardware_adapter import Ros2BridgeProfile
from agentic_runtime.server import RuntimeServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--mock", action="store_true", default=True)
    status.add_argument("--real", action="store_false", dest="mock")
    status.add_argument("--json", action="store_true")

    for name in ("run", "run-app"):
        run_app = sub.add_parser(name)
        run_app.add_argument("app_id")
        run_app.add_argument("--place", default="厨房")
        run_app.add_argument("--mock", action="store_true", default=True)
        run_app.add_argument("--real", action="store_false", dest="mock")
        run_app.add_argument("--json", action="store_true")

    sessions = sub.add_parser("sessions")
    sessions.add_argument("--limit", type=int, default=20)
    sessions.add_argument("--json", action="store_true")

    session = sub.add_parser("session")
    session.add_argument("session_id")
    session.add_argument("--json", action="store_true")

    stop = sub.add_parser("stop")
    stop.add_argument("session_id")
    stop.add_argument("--reason", default="operator_requested")
    stop.add_argument("--json", action="store_true")

    audit = sub.add_parser("audit")
    audit.add_argument("--limit", type=int, default=20)
    audit.add_argument("--json", action="store_true")

    apps = sub.add_parser("apps")
    apps.add_argument("--json", action="store_true")

    skills = sub.add_parser("skills")
    skills.add_argument("--json", action="store_true")

    refresh = sub.add_parser("refresh")
    refresh.add_argument("--json", action="store_true")

    bridge = sub.add_parser("bridge")
    bridge_sub = bridge.add_subparsers(dest="bridge_command", required=True)
    bridge_status = bridge_sub.add_parser("status")
    bridge_status.add_argument("--json", action="store_true")
    bridge_install = bridge_sub.add_parser("install")
    bridge_install.add_argument("--profile", default="ros2_mock")
    bridge_install.add_argument("--json", action="store_true")
    return parser


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


async def run_app(args) -> int:
    server = RuntimeServer.create(mock=args.mock)
    result = await server.scheduler.run_app(args.app_id, place=args.place, mock=args.mock)
    if args.json:
        print_json(result)
    else:
        print(f"session_id={result['session_id']}")
        print(f"app_id={result['app_id']}")
        print(f"status={result['status']}")
        print_json(result)
        success = bool(result.get("result", {}).get("success"))
        print(f"success={'true' if success else 'false'}")
    return 0 if bool(result.get("result", {}).get("success")) else 1


def status(args) -> int:
    server = RuntimeServer.create(mock=args.mock)
    skills = [skill.name for skill in server.registry.list_skills()]
    data = server.monitor.status(skills, ros_bridge=server.config.ros_bridge_mode)
    data["scheduler"] = server.scheduler.status()
    data["sessions"] = [record.to_dict() for record in server.session_manager.list_sessions(limit=5)]
    if args.json:
        print_json(data)
        return 0
    print("agenticd: running")
    print(f"ros_bridge: {data['ros_bridge']}")
    print(f"scheduler: {data['scheduler']['policy']}")
    print("skills:")
    for item in data["skills"]:
        print(f"  - {item['name']}: {item['status']}")
    print("resource_locks:")
    if data["resource_locks"]:
        for name, owner in data["resource_locks"].items():
            print(f"  - {name}: {owner}")
    else:
        print("  - base: free")
    print("recent_syscalls:")
    for record in data["recent_syscalls"]:
        print(f"  - {record.get('skill_name')}: {record.get('status')} {record.get('error_code')}")
    return 0


def sessions(args) -> int:
    server = RuntimeServer.create(mock=True)
    records = server.session_manager.list_sessions(limit=args.limit)
    if args.json:
        print_json([record.to_dict() for record in records])
        return 0
    for record in records:
        print(f"{record.session_id} {record.app_id} {record.status}")
    return 0


def session(args) -> int:
    server = RuntimeServer.create(mock=True)
    record = server.session_manager.get_session(args.session_id)
    if record is None:
        print_json({"success": False, "error_code": "SESSION_NOT_FOUND", "session_id": args.session_id})
        return 1
    data = record.to_dict()
    data["syscalls"] = server.session_manager.read_syscalls(args.session_id, limit=100)
    if args.json:
        print_json(data)
    else:
        print(f"session_id={record.session_id}")
        print(f"app_id={record.app_id}")
        print(f"status={record.status}")
        print(f"current_skill={record.current_skill}")
        print(f"error_code={record.error_code}")
        print("syscalls:")
        for syscall in data["syscalls"]:
            print(f"  - {syscall.get('skill_name')}: {syscall.get('status')} {syscall.get('error_code')}")
    return 0


def stop(args) -> int:
    server = RuntimeServer.create(mock=True)
    try:
        record = server.session_manager.stop_session(args.session_id, reason=args.reason)
    except KeyError:
        print_json({"success": False, "error_code": "SESSION_NOT_FOUND", "session_id": args.session_id})
        return 1
    if args.json:
        print_json(record.to_dict())
    else:
        print(f"session_id={record.session_id}")
        print(f"status={record.status}")
        print(f"stop_requested={'true' if record.stop_requested else 'false'}")
    return 0


def audit(args) -> int:
    server = RuntimeServer.create(mock=True)
    records = server.audit_logger.recent(limit=args.limit)
    if args.json:
        print_json(records)
    else:
        for record in records:
            print(f"{record.get('audit_id')} {record.get('skill_name')} {record.get('status')} {record.get('error_code')}")
    return 0


def apps(args) -> int:
    server = RuntimeServer.create(mock=True)
    records = server.app_factory.list_apps()
    if args.json:
        print_json(records)
    else:
        for record in records:
            print(f"{record['app_id']} {record['version']}")
    return 0


def skills(args) -> int:
    server = RuntimeServer.create(mock=True)
    records = [{"name": skill.name, "version": skill.version} for skill in server.registry.list_skills()]
    if args.json:
        print_json(records)
    else:
        for record in records:
            print(f"{record['name']} {record['version']}")
    return 0


def refresh(args) -> int:
    server = RuntimeServer.create(mock=True)
    result = server.config_manager.refresh()
    if args.json:
        print_json(result.to_dict())
    else:
        print(f"success={'true' if result.success else 'false'}")
        for item in result.reloaded:
            print(f"reloaded={item}")
        for warning in result.warnings:
            print(f"warning={warning}")
        if result.error_code:
            print(f"error_code={result.error_code}")
    return 0 if result.success else 1


def bridge(args) -> int:
    server = RuntimeServer.create(mock=True)
    if args.bridge_command == "status":
        data = server.bridge_manager.status()
    else:
        data = server.bridge_manager.install_profile(Ros2BridgeProfile(name=args.profile))
    if args.json:
        print_json(data)
    else:
        for key, value in data.items():
            print(f"{key}={value}")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {"run", "run-app"}:
        return asyncio.run(run_app(args))
    if args.command == "status":
        return status(args)
    if args.command == "sessions":
        return sessions(args)
    if args.command == "session":
        return session(args)
    if args.command == "stop":
        return stop(args)
    if args.command == "audit":
        return audit(args)
    if args.command == "apps":
        return apps(args)
    if args.command == "skills":
        return skills(args)
    if args.command == "refresh":
        return refresh(args)
    if args.command == "bridge":
        return bridge(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
