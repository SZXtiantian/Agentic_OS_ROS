#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml


APP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TEMPLATE_SOURCE = "agentic_apps/app_template"
TEMPLATE_NAME = "app_template"
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def fail(code: str, message: str) -> int:
    print(f"CREATE_AGENTIC_APP_FAILED {code}: {message}", file=sys.stderr)
    return 1


def valid_name(name: str) -> bool:
    return bool(APP_NAME_RE.fullmatch(name)) and name not in {".", "..", TEMPLATE_NAME}


def copy_template(template_dir: Path, destination: Path) -> None:
    shutil.copytree(
        template_dir,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )


def rewrite_manifest(app_dir: Path, app_name: str, description: str) -> None:
    manifest_path = app_dir / "app.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    data["name"] = app_name
    data["description"] = description
    data["entrypoint"] = "main:run"
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def rewrite_text_files(app_dir: Path, app_name: str) -> None:
    for path in sorted(app_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace(TEMPLATE_NAME, app_name)
        if path.name == "README.md":
            lines = text.splitlines()
            if lines and lines[0].startswith("# "):
                lines[0] = f"# {app_name}"
                text = "\n".join(lines) + ("\n" if path.read_text(encoding="utf-8").endswith("\n") else "")
        path.write_text(text, encoding="utf-8")


def rename_template_tests(app_dir: Path, app_name: str) -> None:
    tests_dir = app_dir / "tests"
    if not tests_dir.exists():
        return
    for path in sorted(tests_dir.glob("*app_template*.py")):
        new_name = path.name.replace(TEMPLATE_NAME, app_name)
        path.rename(path.with_name(new_name))


def write_template_marker(app_dir: Path) -> None:
    (app_dir / ".agentic_template_source").write_text(
        "\n".join(
            [
                f"source={TEMPLATE_SOURCE}",
                f"template_name={TEMPLATE_NAME}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an Agentic App by copying agentic_apps/app_template.")
    parser.add_argument("app_name", help="Directory name under agentic_apps, for example my_agent")
    parser.add_argument("--description", default="", help="Description to write into app.yaml")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing generated app directory")
    args = parser.parse_args(argv)

    app_name = args.app_name.strip()
    if not valid_name(app_name):
        return fail("APP_NAME_INVALID", "app name must match ^[a-z][a-z0-9_]*$ and cannot be app_template")

    root = repo_root()
    template_dir = root / TEMPLATE_SOURCE
    if not template_dir.is_dir():
        return fail("TEMPLATE_MISSING", f"template directory not found: {template_dir}")

    app_dir = root / "agentic_apps" / app_name
    if app_dir.exists():
        if not args.overwrite:
            return fail("APP_ALREADY_EXISTS", f"target exists: {app_dir}")
        marker = app_dir / ".agentic_template_source"
        if not marker.exists() or f"source={TEMPLATE_SOURCE}" not in marker.read_text(encoding="utf-8", errors="ignore"):
            return fail("OVERWRITE_REFUSED", "existing app does not carry the app_template source marker")
        shutil.rmtree(app_dir)

    description = args.description.strip() or f"Template-derived Agentic App named {app_name}."
    copy_template(template_dir, app_dir)
    rewrite_manifest(app_dir, app_name, description)
    rewrite_text_files(app_dir, app_name)
    rename_template_tests(app_dir, app_name)
    write_template_marker(app_dir)

    rel = app_dir.relative_to(root)
    print(f"CREATE_AGENTIC_APP_OK app={app_name} path={rel}")
    print(f"Next: edit {rel}/app.yaml")
    print(f"Next: edit {rel}/main.py")
    print(f"Next: python scripts/check_agentic_app_uses_template.py {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
