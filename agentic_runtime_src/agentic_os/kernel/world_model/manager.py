from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class WorldModel:
    """Physical-world state and place resolver."""

    def __init__(self, places_file: str | Path | None = None) -> None:
        self._places: dict[str, dict[str, Any]] = {}
        self._state: dict[str, Any] = {}
        if places_file is not None:
            self.load_places(places_file)

    def load_places(self, places_file: str | Path) -> None:
        path = Path(places_file)
        if not path.exists():
            return
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.load_places_data(data)

    def load_places_data(self, data: dict[str, Any]) -> None:
        places = data.get("places", data)
        if isinstance(places, list):
            self._places = {str(item.get("name")): item for item in places if isinstance(item, dict) and item.get("name")}
        elif isinstance(places, dict):
            self._places = {str(name): dict(value or {}) for name, value in places.items()}

    def resolve_place(self, name: str) -> dict[str, Any]:
        place = self._places.get(name)
        if place is None:
            return {"success": False, "error_code": "PLACE_NOT_FOUND", "place": name}
        return {"success": True, "place": name, "target": place}

    def set_state(self, key: str, value: Any) -> dict[str, Any]:
        self._state[key] = value
        return {"success": True, "key": key}

    def get_state(self, key: str | None = None) -> dict[str, Any]:
        if key is None:
            return {"success": True, "state": dict(self._state)}
        return {"success": key in self._state, "key": key, "value": self._state.get(key)}
