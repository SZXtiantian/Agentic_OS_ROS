from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.llm_core import response_text
from agentic_os.kernel.memory import ConversationExtractor
from agentic_runtime.audit import AuditLogger
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def test_kernel_e2e_llm_memory_storage_flow(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    service = KernelService(
        config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"),
        audit_logger=audit,
    )

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("kernel e2e flow should not call skill executor")

    async def run():
        app = AppManifest("e2e_kernel_app", "0", "", "main:run", [], [])
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
        assert any(record["skill_name"] == "kernel.llm.chat" for record in audit_records)
        assert any(record["skill_name"] == "kernel.memory.remember" for record in audit_records)
        assert any(record["skill_name"] == "kernel.storage.sto_write" for record in audit_records)

    asyncio.run(run())
