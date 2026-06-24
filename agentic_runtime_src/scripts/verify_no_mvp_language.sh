#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python - <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
TERMS = re.compile(r"\bmvp\b|minimum viable|最小可用|最小版本", re.IGNORECASE)
ACTIVE_ROOTS = [
    Path("AGENTS.md"),
    Path("README.md"),
    Path("pyproject.toml"),
    Path("setup.py"),
    Path("agentic_runtime"),
    Path("agentic_os"),
    Path("configs"),
    Path("docs"),
    Path("scripts"),
    Path("tests"),
    ROOT.parent / "AGENTS.md",
    ROOT.parent / "README.md",
    ROOT.parent / "agentic_apps",
    ROOT.parent / "ros2_bridge_src",
]
LEGACY_DOCS = {
    Path("CODEX_IMPLEMENTATION_TASKBOOK.md"),
    Path("docs/codex_kernel_phase2_progress.md"),
    Path("docs/codex_kernel_port_progress.md"),
    Path("scripts/run_tests.sh"),
    Path("scripts/verify_no_mvp_language.sh"),
    Path("tests/test_no_mvp_language.py"),
}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".sh",
    ".json",
    ".txt",
}


def iter_files(path: Path):
    if not path.exists():
        return
    if path.is_file():
        yield path
        return
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        if any(part in SKIP_PARTS for part in child.parts):
            continue
        if child.suffix.lower() in TEXT_SUFFIXES:
            yield child


def relpath(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


failures: list[str] = []
for root in ACTIVE_ROOTS:
    root_path = root if root.is_absolute() else ROOT / root
    for path in iter_files(root_path):
        rel = relpath(path)
        if rel in LEGACY_DOCS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if TERMS.search(line):
                failures.append(f"{rel}:{lineno}: {line.strip()}")

if failures:
    print("NO_MVP_LANGUAGE_FAILED")
    for failure in failures:
        print(failure)
    sys.exit(1)

print("NO_MVP_LANGUAGE_OK foundation-complete language verified")
PY
