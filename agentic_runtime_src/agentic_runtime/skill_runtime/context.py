from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SkillRuntimeContext:
    app_id: str
    session_id: str
    call_id: str = ""
    cancel_event: Any = None
    bridge_client: Any = None
    memory_store: Any = None
    human_channel: Any = None
