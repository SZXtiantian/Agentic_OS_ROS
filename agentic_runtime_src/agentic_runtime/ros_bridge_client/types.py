from __future__ import annotations

from typing import Any, Protocol


class RosBridgeClient(Protocol):
    async def resolve_place(self, name: str) -> dict[str, Any]: ...

    async def get_robot_state(self) -> dict[str, Any]: ...

    async def check_safety(self, skill_name: str, args: dict[str, Any], app_id: str) -> dict[str, Any]: ...

    async def navigate_to(self, place: str, timeout_s: int, cancel_event=None) -> dict[str, Any]: ...

    async def inspect_area(self, place: str, timeout_s: int) -> dict[str, Any]: ...

    async def observe(self, target: str, timeout_s: int) -> dict[str, Any]: ...

    async def capture_photo(self, target: str, label: str, timeout_s: int) -> dict[str, Any]: ...

    async def center_color_block(self, color: str, target: str, evidence_label: str, timeout_s: int) -> dict[str, Any]: ...

    async def detect_color_block(self, color: str, target: str, evidence_label: str, timeout_s: int) -> dict[str, Any]: ...

    async def verify_held_color_block(
        self,
        color: str,
        target: str,
        detection: dict[str, Any],
        pick_result: dict[str, Any],
        evidence_label: str,
        timeout_s: int,
    ) -> dict[str, Any]: ...

    async def get_arm_state(self) -> dict[str, Any]: ...

    async def move_arm_named(self, name: str, timeout_s: int, cancel_event=None) -> dict[str, Any]: ...

    async def set_gripper(self, command: str, force: str = "low", percentage: float | None = None, timeout_s: int = 5) -> dict[str, Any]: ...

    async def pick_color_block(
        self,
        color: str,
        target: str,
        detection: dict[str, Any],
        evidence: dict[str, Any],
        timeout_s: int,
    ) -> dict[str, Any]: ...

    async def place_color_block(
        self,
        color: str,
        place_target: str,
        pick_result: dict[str, Any],
        timeout_s: int,
    ) -> dict[str, Any]: ...

    async def stop_robot(self, reason: str) -> dict[str, Any]: ...

    async def ask_human(self, question: str, options=None, timeout_s: int = 60, require_confirmation: bool = False) -> dict[str, Any]: ...

    async def report_say(self, message: str) -> dict[str, Any]: ...
