#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path.cwd()
ALLOWLIST = ROOT / "scripts" / "no_fake_mock_allowlist.txt"
PRODUCTION_ROOTS = [
    ROOT / "agentic_os",
    ROOT / "agentic_runtime",
    ROOT / "configs",
    ROOT / "scripts",
    ROOT / "system_skills",
    ROOT.parent / "agentic_apps",
    ROOT.parent / "ros2_bridge_src",
    Path("/home/ubuntu/agentic_ws/ros2_bridge_src"),
    ROOT.parent / "scripts",
]
TEST_ROOTS = [ROOT / "tests"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".sh", ".json", ".txt", ".md", ".toml"}
PRODUCTION_PATTERNS = {
    "forbidden backend class": re.compile(r"class\s+\w*(?:Mock|Fake|Stub|Dummy)\w*(?:Provider|Backend|Client|Bridge|Manager)\b"),
    "forbidden backend symbol": re.compile(r"\b(?:Mock|Fake|Stub|Dummy)\w*(?:Provider|Backend|Client|Bridge|Manager)\b"),
    "forbidden backend config": re.compile(r"\b(?:backend|type)\s*[:=]\s*['\"]?(?:mock|fake|stub|dummy)['\"]?", re.IGNORECASE),
    "forbidden success text": re.compile(r"\b(?:mock|fake|stub|dummy)[_\s-]*(?:success|camera|bridge|provider|backend)\b", re.IGNORECASE),
    "hardcoded success": re.compile(r"hardcoded\s+success", re.IGNORECASE),
    "rule planner fallback": re.compile(r"rule\s+planner\s+fallback", re.IGNORECASE),
    "simulated success": re.compile(r"simulated\s+success", re.IGNORECASE),
}
TEST_PATTERNS = {
    "patched scheduler success": re.compile(r"monkeypatch.*(?:llm|capability|skill|tool|memory|storage).*success", re.IGNORECASE),
    "MagicMock success": re.compile(r"MagicMock\(.*success\s*=\s*True", re.IGNORECASE),
}


def load_allowlist() -> list[tuple[re.Pattern[str], re.Pattern[str], str]]:
    entries: list[tuple[re.Pattern[str], re.Pattern[str], str]] = []
    if not ALLOWLIST.exists():
        return entries
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path_pattern, regex, reason = line.split("|", 2)
        entries.append((re.compile(path_pattern), re.compile(regex, re.IGNORECASE), reason))
    return entries


ALLOW = load_allowlist()


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return path.relative_to(ROOT.parent).as_posix()
        except ValueError:
            return path.as_posix()


def iter_files(root: Path):
    if not root.exists():
        return
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def allowed(path_text: str, text: str, match_text: str) -> bool:
    for path_pattern, regex, _reason in ALLOW:
        if path_pattern.search(path_text) and (regex.search(match_text) or regex.search(text)):
            return True
    return False


failures: list[str] = []
for root in PRODUCTION_ROOTS:
    for path in iter_files(root):
        path_text = rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PRODUCTION_PATTERNS.items():
            for match in pattern.finditer(text):
                if not allowed(path_text, text, match.group(0)):
                    failures.append(f"{path_text}: {label}: {match.group(0)!r}")

for root in TEST_ROOTS:
    for path in iter_files(root):
        path_text = rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in TEST_PATTERNS.items():
            for match in pattern.finditer(text):
                if not allowed(path_text, text, match.group(0)):
                    failures.append(f"{path_text}: {label}: {match.group(0)!r}")

print("CHECK_NAME=no_fake_mock")
if failures:
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_FAKE_MOCK_FORBIDDEN")
    print("NEXT_ACTION=remove forbidden success path or add a narrow allowlist entry only for rejecting/documenting it")
    for failure in failures:
        print(failure)
    sys.exit(1)

print("RESULT=PASS")
print("ERROR_CODE=")
print("NEXT_ACTION=")
PY
