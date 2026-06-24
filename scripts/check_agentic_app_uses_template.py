#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import yaml


CORE_PATHS = [
    "README.md",
    "app.yaml",
    "main.py",
    "prompts/system.md",
    "storage/.gitkeep",
    "workflows/default.yaml",
]
MARKER_LINES = {
    "source=agentic_apps/app_template",
    "template_name=app_template",
}


def _load_tree(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None


def _has_async_run(tree: ast.AST | None) -> bool:
    if tree is None:
        return False
    return any(isinstance(node, ast.AsyncFunctionDef) and node.name == "run" for node in ast.walk(tree))


def _uses_agent_context(tree: ast.AST | None, text: str) -> bool:
    if tree is None:
        return False
    imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "agentic_runtime.sdk":
            imported = any(alias.name == "AgentContext" for alias in node.names)
        if isinstance(node, ast.Name) and node.id == "AgentContext":
            return True
    return imported and "AgentContext" in text


def check(app_dir: Path) -> list[str]:
    errors: list[str] = []
    if not app_dir.is_dir():
        return [f"APP_DIR_MISSING: {app_dir}"]

    for rel in CORE_PATHS:
        if not (app_dir / rel).exists():
            errors.append(f"CORE_FILE_MISSING: {rel}")
    if not (app_dir / "tests").is_dir():
        errors.append("CORE_DIR_MISSING: tests")
    elif not any((app_dir / "tests").glob("*.py")):
        errors.append("TESTS_MISSING: tests must contain at least one Python test")

    marker = app_dir / ".agentic_template_source"
    if not marker.exists():
        errors.append("TEMPLATE_MARKER_MISSING: .agentic_template_source")
    else:
        marker_lines = {line.strip() for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()}
        missing = sorted(MARKER_LINES - marker_lines)
        for line in missing:
            errors.append(f"TEMPLATE_MARKER_INVALID: missing {line}")

    manifest_path = app_dir / "app.yaml"
    if manifest_path.exists():
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if data.get("entrypoint") != "main:run":
            errors.append("ENTRYPOINT_INVALID: app.yaml must set entrypoint: main:run")
    main_path = app_dir / "main.py"
    if main_path.exists():
        text = main_path.read_text(encoding="utf-8")
        tree = _load_tree(main_path)
        if not _has_async_run(tree):
            errors.append("ASYNC_RUN_MISSING: main.py must expose async def run")
        if not _uses_agent_context(tree, text):
            errors.append("AGENT_CONTEXT_MISSING: main.py must use AgentContext")
        denial_phrases = (
            "not derived from app_template",
            "not from app_template",
            "not copied from agentic_apps/app_template",
        )
        lower_text = text.lower()
        for phrase in denial_phrases:
            if phrase in lower_text:
                errors.append(f"TEMPLATE_DERIVATION_DENIED: {phrase}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that an Agentic App keeps the canonical app_template structure.")
    parser.add_argument("app_dir", type=Path)
    args = parser.parse_args(argv)
    errors = check(args.app_dir)
    if errors:
        print("AGENTIC_APP_TEMPLATE_CHECK_FAILED")
        for error in errors:
            print(error)
        return 1
    print(f"AGENTIC_APP_TEMPLATE_CHECK_OK path={args.app_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
