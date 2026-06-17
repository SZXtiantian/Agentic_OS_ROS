from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import KernelSyscall


@runtime_checkable
class KernelRequestHandler(Protocol):
    def address_request(self, syscall: KernelSyscall) -> Any:
        ...
