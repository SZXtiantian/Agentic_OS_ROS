import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SRC = REPO_ROOT / "agentic_runtime_src"
APP_ROOT = REPO_ROOT / "agentic_apps"
AGENTIC_HOME = REPO_ROOT / ".agentic_home"

os.environ.setdefault("AGENTIC_RUNTIME_SRC", str(RUNTIME_SRC))
os.environ.setdefault("AGENTIC_APP_ROOT", str(APP_ROOT))
os.environ.setdefault("AGENTIC_SKILLS", str(RUNTIME_SRC / "skills"))
os.environ.setdefault("AGENTIC_HOME", str(AGENTIC_HOME))
os.environ.setdefault("AGENTIC_VAR", str(AGENTIC_HOME / "var"))
os.environ.setdefault("AGENTIC_ETC", str(AGENTIC_HOME / "etc"))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def runtime_src() -> Path:
    return RUNTIME_SRC


@pytest.fixture
def app_root() -> Path:
    return APP_ROOT


@pytest.fixture
def robot_photographer_app_dir(app_root: Path) -> Path:
    return app_root / "robot_photographer_agent"
