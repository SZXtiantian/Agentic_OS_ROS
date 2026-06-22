from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class CombinedCancellationEvent:
    session_event: asyncio.Event
    call_event: asyncio.Event

    def is_set(self) -> bool:
        return self.session_event.is_set() or self.call_event.is_set()


class CancellationManager:
    def __init__(self) -> None:
        self._session_events: dict[str, asyncio.Event] = {}
        self._call_events: dict[tuple[str, str], asyncio.Event] = {}

    def event_for(self, session_id: str, call_id: str = ""):
        event = self._session_events.get(session_id)
        if event is None or event.is_set():
            event = asyncio.Event()
            self._session_events[session_id] = event
        if not call_id:
            return event
        call_key = (session_id, call_id)
        call_event = self._call_events.get(call_key)
        if call_event is None or call_event.is_set():
            call_event = asyncio.Event()
            self._call_events[call_key] = call_event
        return CombinedCancellationEvent(event, call_event)

    def cancel_session(self, session_id: str) -> None:
        self.event_for(session_id).set()

    def cancel_call(self, session_id: str, call_id: str) -> bool:
        event = self._call_events.get((session_id, call_id))
        if event is None:
            return False
        event.set()
        return True

    def clear_call(self, session_id: str, call_id: str) -> None:
        self._call_events.pop((session_id, call_id), None)

    def active_calls(self) -> list[dict[str, str]]:
        return [
            {"session_id": session_id, "call_id": call_id}
            for session_id, call_id in sorted(self._call_events)
        ]

    def cancel_all(self) -> None:
        for event in self._session_events.values():
            event.set()
        for event in self._call_events.values():
            event.set()
