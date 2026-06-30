from __future__ import annotations

from agentic_os.kernel.scheduler import (
    EnvironmentAwareDAGScheduler,
    FIFOKernelScheduler,
    FIFORequestScheduler,
    RoundRobinKernelScheduler,
    RoundRobinRequestScheduler,
)
from agentic_runtime.kernel_service import KernelService


class Config:
    scheduler_policy = "fifo"
    storage_root = "/tmp/agentic_scheduler_compat"

    def __init__(self, policy: str) -> None:
        self.kernel = {"scheduler_policy": policy}


def test_request_scheduler_exports_remain_compatible():
    fifo = FIFORequestScheduler()
    rr = RoundRobinRequestScheduler()

    assert fifo.status()["policy"] == "fifo"
    assert rr.status()["policy"] == "round_robin"


def test_kernel_scheduler_policy_defaults_and_explicit_env_dag():
    fifo_service = KernelService(config=Config("fifo"))
    rr_service = KernelService(config=Config("round_robin"))
    dag_service = KernelService(config=Config("env_aware_priority_dag"))

    assert isinstance(fifo_service.scheduler, FIFOKernelScheduler)
    assert isinstance(rr_service.scheduler, RoundRobinKernelScheduler)
    assert isinstance(dag_service.scheduler, EnvironmentAwareDAGScheduler)
    assert dag_service.status()["scheduler"]["policy"] == "env_aware_priority_dag"
