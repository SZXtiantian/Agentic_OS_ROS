from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], Any]


def builtin_tools(workspace_root: str | Path | None = None) -> dict[str, tuple[ToolHandler, str]]:
    root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    return {
        "calculator.add": (_calculator_add, "Add two numeric values."),
        "format_report.markdown": (_format_report_markdown, "Render a markdown report from a title and sections."),
        "file_digest.sha256": (_file_digest_sha256(root), "Calculate a SHA-256 digest for a file inside the tool workspace."),
    }


def _calculator_add(args: dict[str, Any]) -> dict[str, Any]:
    a = args.get("a", 0)
    b = args.get("b", 0)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("calculator.add expects numeric a and b")
    return {"value": a + b}


def _format_report_markdown(args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "Report")
    sections = args.get("sections") or []
    lines = [f"# {title}", ""]
    if isinstance(sections, dict):
        iterable = sections.items()
    else:
        iterable = []
        for item in sections:
            if isinstance(item, dict):
                iterable.append((str(item.get("heading") or item.get("title") or "Section"), item.get("body", "")))
            else:
                iterable.append(("Section", item))
    for heading, body in iterable:
        lines.extend([f"## {heading}", "", str(body), ""])
    markdown = "\n".join(lines).strip() + "\n"
    return {"markdown": markdown}


def _file_digest_sha256(root: Path) -> ToolHandler:
    def digest(args: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(args.get("path") or "")
        if not raw_path:
            raise ValueError("file_digest.sha256 requires path")
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if root not in path.parents and path != root:
            raise ValueError("file_digest.sha256 path outside workspace")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "path": str(path)}

    return digest
