# Scheduler

The scheduler package contains two layers:

- Legacy `FIFORequestScheduler` and `RoundRobinRequestScheduler`, kept for existing runtime wrappers.
- Kernel scheduler v2, where `FIFOKernelScheduler` starts module processing threads that consume named kernel queues and call each manager's `address_request(syscall)`.

Robot motion uses a dedicated non-preemptible `robot_motion` lane with one worker by default. Generic tools stay on the `tool` lane and must not expose robot capabilities.

Contract module for AgenticOS scheduling and session execution.
