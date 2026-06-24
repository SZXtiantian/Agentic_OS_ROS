from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repository_agentic_app_boundary_script_accepts_current_apps():
    result = subprocess.run(
        [sys.executable, "scripts/check_agentic_app_boundaries.py", "agentic_apps"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "AGENTIC_APP_BOUNDARY_CHECK_OK" in result.stdout
