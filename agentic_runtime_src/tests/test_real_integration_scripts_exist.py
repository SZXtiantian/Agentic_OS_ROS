from __future__ import annotations

import os
import subprocess
from pathlib import Path


REAL_SCRIPTS = [
    "verify_real_ros2.sh",
    "verify_real_llm.sh",
    "verify_real_human.sh",
]


def test_foundation_verification_scripts_exist_and_are_executable(runtime_src: Path):
    for name in [
        "verify_foundation.sh",
        "verify_capability_truth.sh",
        "verify_no_mvp_language.sh",
        *REAL_SCRIPTS,
    ]:
        path = runtime_src / "scripts" / name
        assert path.exists(), name
        assert os.access(path, os.X_OK), name


def test_real_dependency_scripts_report_unverified_without_env(runtime_src: Path):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("AGENTIC_VERIFY_REAL_") or key.startswith("AGENTIC_REAL_LLM_"):
            env.pop(key)

    for name in REAL_SCRIPTS:
        result = subprocess.run(
            [str(runtime_src / "scripts" / name)],
            cwd=runtime_src,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 2, result.stderr
        assert "UNVERIFIED_REAL_DEPENDENCY" in result.stdout
