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
    dag_alias_service = KernelService(config=Config("environment_aware_dag"))

    assert isinstance(fifo_service.scheduler, FIFOKernelScheduler)
    assert isinstance(rr_service.scheduler, RoundRobinKernelScheduler)
    assert isinstance(dag_service.scheduler, EnvironmentAwareDAGScheduler)
    assert isinstance(dag_alias_service.scheduler, EnvironmentAwareDAGScheduler)
    assert dag_service.status()["scheduler"]["policy"] == "env_aware_priority_dag"
    assert dag_alias_service.status()["scheduler"]["policy"] == "environment_aware_dag"


def test_environment_aware_scheduler_status_exposes_required_runtime_counters():
    service = KernelService(config=Config("environment_aware_dag"))

    status = service.status()["scheduler"]

    assert status["policy"] == "environment_aware_dag"
    assert status["graph_revision"] == status["global_revision"]
    for key in ("ready", "running", "blocked", "completed", "failed", "lease_count", "fact_count"):
        assert key in status
        assert isinstance(status[key], int)
    assert status["lane_capacity"]
