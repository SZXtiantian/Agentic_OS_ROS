from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_os.kernel.system_call import ContextQuery, KernelResponse, KernelSyscall

from .providers import ContextProvider, SQLiteContextProvider


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContextSnapshot:
    session_id: str
    agent_name: str
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __getattr__(self, name: str) -> Any:
        if name in self.state:
            return self.state[name]
        raise AttributeError(name)


class ContextManager:
    """Persistent syscall-facing context manager.

    Context is short-lived execution state, not semantic memory. The default
    provider is a real SQLite database so context survives process restarts and
    can be inspected through status/audit events.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        provider: ContextProvider | None = None,
        *,
        default_session_id: str = "default",
    ) -> None:
        self.root = Path(root or "/tmp/agentic_kernel_context")
        self.provider = provider or SQLiteContextProvider(self.root / "context.sqlite3")
        self.default_session_id = default_session_id
        self._events: list[dict[str, Any]] = []

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        query = getattr(syscall, "query", None)
        if not isinstance(query, ContextQuery):
            query = ContextQuery(
                operation_type=syscall.operation_type,
                params=dict(syscall.params),
                namespace=str(syscall.params.get("namespace") or "context"),
                session_id=str(syscall.params.get("session_id") or self.default_session_id),
                checkpoint=str(syscall.params.get("checkpoint") or ""),
            )
        owner = syscall.agent_name
        session_id = query.session_id or str(query.params.get("session_id") or self.default_session_id)
        namespace = query.namespace or str(query.params.get("namespace") or "context")
        op = self._normalize_operation(query.operation_type)
        params = dict(query.params)
        try:
            if op == "ctx_put":
                response = self._put(owner, session_id, namespace, params)
            elif op == "ctx_get":
                response = self._get(owner, session_id, namespace, params)
            elif op == "ctx_delete":
                response = self._delete(owner, session_id, namespace, params)
            elif op == "ctx_list":
                response = self._list(owner, session_id, namespace, params)
            elif op == "ctx_snapshot":
                response = self._snapshot(owner, session_id, query.checkpoint, params, syscall)
            elif op == "ctx_recover":
                response = self._recover(owner, session_id, query.checkpoint, params)
            elif op == "ctx_compact":
                response = self._compact(owner, session_id, namespace, params)
            elif op == "ctx_clear":
                response = self._clear(owner, session_id, namespace, params)
            else:
                response = KernelResponse.error(
                    "CONTEXT_OPERATION_UNSUPPORTED",
                    metadata={"operation_type": query.operation_type},
                )
        except Exception as exc:
            response = KernelResponse.error(
                "CONTEXT_PROVIDER_UNAVAILABLE",
                metadata={"reason": str(exc), "provider_status": self.provider.status()},
            )
        self._record_event(owner, op, response)
        return response

    def snapshot(self, session_id: str, agent_name: str, **state: Any) -> ContextSnapshot:
        result = self.provider.snapshot(agent_name, session_id, "manual", dict(state), {"compat": True})
        if not result.get("success", False):
            raise RuntimeError(str(result.get("error_code") or "CONTEXT_SNAPSHOT_FAILED"))
        return ContextSnapshot(session_id=session_id, agent_name=agent_name, state=dict(state), created_at=result["created_at"])

    def recover(self, session_id: str, agent_name: str = "", checkpoint: str = "") -> ContextSnapshot | None:
        owner = agent_name or self._latest_owner_for_session(session_id)
        if not owner:
            return None
        result = self.provider.recover(owner, session_id, checkpoint)
        if result is None:
            return None
        return ContextSnapshot(
            session_id=session_id,
            agent_name=owner,
            state=dict(result.get("state") or {}),
            created_at=str(result.get("created_at") or ""),
        )

    def status(self) -> dict[str, Any]:
        return {
            **self.provider.status(),
            "recent_events": list(self._events[-20:]),
        }

    def _put(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        key = str(params.get("key") or "")
        if not key:
            return KernelResponse.error("CONTEXT_KEY_REQUIRED")
        metadata = dict(params.get("metadata") or {})
        if "ttl_s" in params:
            metadata["ttl_s"] = params["ttl_s"]
        result = self.provider.put(owner, session_id, namespace, key, params.get("value"), metadata)
        return self._provider_response(result)

    def _get(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        key = str(params.get("key") or "")
        if not key:
            return KernelResponse.error("CONTEXT_KEY_REQUIRED")
        result = self.provider.get(owner, session_id, namespace, key)
        if result is None:
            return KernelResponse.error("CONTEXT_NOT_FOUND", metadata={"key": key})
        return KernelResponse.ok(result, data=result)

    def _delete(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        key = str(params.get("key") or "")
        if not key:
            return KernelResponse.error("CONTEXT_KEY_REQUIRED")
        deleted = self.provider.delete(owner, session_id, namespace, key)
        if not deleted:
            return KernelResponse.error("CONTEXT_NOT_FOUND", metadata={"key": key})
        return KernelResponse.ok({"key": key, "deleted": True})

    def _list(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        entries = self.provider.list(
            owner,
            session_id,
            namespace,
            prefix=str(params.get("prefix") or ""),
            limit=int(params.get("limit", 100)),
        )
        return KernelResponse.ok({"entries": entries}, data={"entries": entries})

    def _snapshot(
        self,
        owner: str,
        session_id: str,
        checkpoint: str,
        params: dict[str, Any],
        syscall: KernelSyscall,
    ) -> KernelResponse:
        metadata = dict(params.get("metadata") or {})
        metadata.update({"pid": syscall.get_pid() or "", "syscall_id": syscall.syscall_id})
        result = self.provider.snapshot(
            owner,
            session_id,
            checkpoint or str(params.get("checkpoint") or "default"),
            dict(params.get("state") or {}),
            metadata,
        )
        return self._provider_response(result)

    def _recover(self, owner: str, session_id: str, checkpoint: str, params: dict[str, Any]) -> KernelResponse:
        result = self.provider.recover(owner, session_id, checkpoint or str(params.get("checkpoint") or ""))
        if result is None:
            return KernelResponse.error("CONTEXT_NOT_FOUND", metadata={"session_id": session_id})
        return KernelResponse.ok(result, data=result)

    def _compact(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        result = self.provider.compact(owner, session_id, namespace, int(params.get("max_tokens", 2000)))
        return self._provider_response(result)

    def _clear(self, owner: str, session_id: str, namespace: str, params: dict[str, Any]) -> KernelResponse:
        scope = str(params.get("scope") or "session")
        deleted_count = self.provider.clear(owner, session_id, scope, namespace)
        return KernelResponse.ok({"deleted_count": deleted_count, "scope": scope})

    def _provider_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "CONTEXT_PROVIDER_UNAVAILABLE"), metadata=result)

    def _normalize_operation(self, operation_type: str) -> str:
        aliases = {
            "snapshot": "ctx_snapshot",
            "recover": "ctx_recover",
            "put": "ctx_put",
            "get": "ctx_get",
            "delete": "ctx_delete",
            "list": "ctx_list",
            "compact": "ctx_compact",
            "clear": "ctx_clear",
        }
        return aliases.get(operation_type, operation_type)

    def _record_event(self, owner: str, operation_type: str, response: KernelResponse) -> None:
        self._events.append(
            {
                "created_at": utc_now(),
                "owner_agent": owner,
                "operation_type": operation_type,
                "success": response.success,
                "error_code": response.error_code,
            }
        )
        self._events = self._events[-100:]

    def _latest_owner_for_session(self, session_id: str) -> str:
        status = self.provider.status()
        if status.get("state") != "ready":
            return ""
        # Compatibility recovery is only used by older direct callers. The
        # syscall path always passes owner explicitly, so this slow scan is kept
        # intentionally narrow and observable.
        try:
            import sqlite3

            path = str(status.get("path") or "")
            if not path:
                return ""
            conn = sqlite3.connect(path)
            row = conn.execute(
                """
                SELECT owner_agent
                FROM context_snapshots
                WHERE session_id=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            conn.close()
            return str(row[0]) if row else ""
        except Exception:
            return ""
