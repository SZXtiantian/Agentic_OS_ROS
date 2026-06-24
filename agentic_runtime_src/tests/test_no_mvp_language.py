from __future__ import annotations

import subprocess
from pathlib import Path


def test_no_mvp_language_guard_passes(runtime_src: Path):
    result = subprocess.run(
        [str(runtime_src / "scripts" / "verify_no_mvp_language.sh")],
        cwd=runtime_src,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "NO_MVP_LANGUAGE_OK" in result.stdout
