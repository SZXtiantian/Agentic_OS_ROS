from __future__ import annotations

import hashlib
import json
from threading import RLock
from typing import Any

from .generation import GenerationSnapshot


class SimpleGenerationContextManager:
    """Logical generation context snapshots without optional KV-cache deps."""

    def __init__(self) -> None:
        self._snapshots: dict[str, GenerationSnapshot] = {}
        self._lock = RLock()

    def save(
        self,
        generation_id: str,
        syscall_id: str,
        prompt: Any,
        partial_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationSnapshot:
        snapshot = GenerationSnapshot(
            generation_id=generation_id,
            syscall_id=syscall_id,
            prompt_hash=self.prompt_hash(prompt),
            partial_response=partial_response,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._snapshots[generation_id] = snapshot
        return snapshot

    def restore(self, generation_id: str) -> GenerationSnapshot | None:
        with self._lock:
            return self._snapshots.get(generation_id)

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()

    def prompt_hash(self, prompt: Any) -> str:
        payload = json.dumps(prompt, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
