from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id

from .preconditions import Precondition
from .task_graph import TaskGraph


@dataclass(frozen=True)
class OpportunityWindow:
    window_id: str
    route_segment_id: str
    workspace_zone: str
    start_after_node_id: str
    end_before_node_id: str
    available_resources: list[str] = field(default_factory=list)
    required_preconditions: list[Precondition] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_preconditions"] = [item.to_dict() for item in self.required_preconditions]
        return data


class OpportunityIndex:
    def __init__(self) -> None:
        self._windows: dict[str, OpportunityWindow] = {}
        self._window_graph_ids: dict[str, str] = {}

    def rebuild_from_graph(self, graph: TaskGraph) -> None:
        self._remove_graph_windows(graph.task_graph_id)
        successors = graph.precedence_edges()
        for node in graph.nodes.values():
            if not node.route_segment_id and not node.workspace_zone:
                continue
            resources = [request.resource_id for request in node.resources]
            end_before = _first_successor(successors.get(node.node_id, set()))
            window = OpportunityWindow(
                window_id=monotonic_id("window"),
                route_segment_id=node.route_segment_id or "",
                workspace_zone=node.workspace_zone or "",
                start_after_node_id=node.node_id,
                end_before_node_id=end_before,
                available_resources=resources,
                required_preconditions=list(node.preconditions),
                score=(10 if node.workspace_zone else 0) + (5 if end_before else 0) + len(resources),
            )
            self._windows[window.window_id] = window
            self._window_graph_ids[window.window_id] = graph.task_graph_id

    def find(self, *, workspace_zone: str = "", route_segment_id: str = "") -> list[OpportunityWindow]:
        matches: list[OpportunityWindow] = []
        for window in self._windows.values():
            if workspace_zone and window.workspace_zone != workspace_zone:
                continue
            if route_segment_id and window.route_segment_id != route_segment_id:
                continue
            matches.append(window)
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def snapshot(self) -> list[dict[str, Any]]:
        return [window.to_dict() for window in sorted(self._windows.values(), key=lambda item: item.window_id)]

    def _remove_graph_windows(self, task_graph_id: str) -> None:
        stale_window_ids = [window_id for window_id, graph_id in self._window_graph_ids.items() if graph_id == task_graph_id]
        for window_id in stale_window_ids:
            self._windows.pop(window_id, None)
            self._window_graph_ids.pop(window_id, None)


def _first_successor(successors: set[str]) -> str:
    return sorted(str(node_id) for node_id in successors if node_id)[0] if successors else ""
