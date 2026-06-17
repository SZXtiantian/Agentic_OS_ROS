"""Kernel queue hooks adapted from AIOS for AgenticOS module scheduling."""

from .queues import KernelQueueStore
from .stores import (
    get_global_queue_store,
    global_queue_add_message,
    global_queue_get_message,
    reset_global_queue_store_for_tests,
)
from .types import DEFAULT_KERNEL_QUEUES, KernelQueueName

__all__ = [
    "DEFAULT_KERNEL_QUEUES",
    "KernelQueueName",
    "KernelQueueStore",
    "get_global_queue_store",
    "global_queue_add_message",
    "global_queue_get_message",
    "reset_global_queue_store_for_tests",
]
