from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_os.kernel.llm_core import response_text
from agentic_os.kernel.memory import ConversationExtractor
from agentic_runtime.audit import AuditLogger
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        content = body.get("messages", [{}])[-1].get("content", "ok")
        raw = json.dumps({"choices": [{"message": {"role": "assistant", "content": f"summary: {content}"}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return


def test_kernel_e2e_llm_memory_storage_flow(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    llm_server = HTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    thread = threading.Thread(target=llm_server.serve_forever, daemon=True)
    thread.start()
    service = KernelService(
        config=SimpleNamespace(
            storage_root=tmp_path / "storage",
            tool_root=tmp_path / "tools",
            kernel={
                "llm": {
                    "configs": [
                        {
                            "name": "local-openai",
                            "backend": "openai_compatible",
                            "base_url": f"http://127.0.0.1:{llm_server.server_port}/v1",
                            "api_key": "test-key",
                            "model": "local-chat",
                            "capabilities": ["chat", "complete"],
                        }
                    ]
                }
            },
        ),
        audit_logger=audit,
    )
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("kernel e2e flow should not call skill executor")

    async def run():
        app = AppManifest("e2e_kernel_app", "0", "", "main:run", ["llm.external.call"], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_e2e")
        service.start()
        try:
            llm_result = await ctx.kernel.llm.chat(
                messages=[{"role": "user", "content": "summarize the kitchen inspection"}],
                timeout_s=1.0,
            )
            assert llm_result.success is True

            assistant_message = response_text(llm_result.response)
            extractor = ConversationExtractor(service.memory)
            note = extractor.extract_async(app.name, "summarize the kitchen inspection", assistant_message)

            memory_result = await ctx.kernel.memory.add(
                "kitchen inspection summary is ready",
                key="inspection-summary",
                tags=["inspection", "report"],
                timeout_s=1.0,
            )
            assert memory_result.success is True

            storage_result = await ctx.kernel.storage.write(
                "reports/e2e.md",
                {"llm_success": llm_result.success, "conversation_memory_id": note.id},
                timeout_s=1.0,
            )
            assert storage_result.success is True
        finally:
            service.stop()

        retrieved = service.memory.retrieve(app.name, "inspection", limit=5)
        report = service.storage.read("reports/e2e.md")
        status = service.status()
        audit_records = audit.recent(limit=10)

        assert retrieved["success"] is True
        assert any(item["id"] == note.id for item in retrieved["memories"])
        assert report["success"] is True
        assert "conversation_memory_id" in report["content"]
        assert any(record["operation_type"] == "sto_write" for record in status["recent_syscalls"])
        assert any(record["skill_name"] == "kernel.llm.llm_chat" for record in audit_records)
        assert any(record["skill_name"] == "kernel.memory.mem_remember" for record in audit_records)
        assert any(record["skill_name"] == "kernel.storage.sto_write" for record in audit_records)

    try:
        asyncio.run(run())
    finally:
        llm_server.shutdown()
