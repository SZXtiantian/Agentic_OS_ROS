from __future__ import annotations

import asyncio


class CancellationManager:
    def __init__(self) -> None:
        self._session_events: dict[str, asyncio.Event] = {}

    def event_for(self, session_id: str) -> asyncio.Event:
        event = self._session_events.get(session_id)
        if event is None or event.is_set():
            event = asyncio.Event()
            self._session_events[session_id] = event
        return event

    def cancel_session(self, session_id: str) -> None:
        self.event_for(session_id).set()

    def cancel_all(self) -> None:
        for event in self._session_events.values():
            event.set()
