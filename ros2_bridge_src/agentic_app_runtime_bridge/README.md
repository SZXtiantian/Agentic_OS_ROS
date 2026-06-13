# agentic_app_runtime_bridge

MVP Runtime currently calls the world, safety, and capability bridge contracts through the Runtime bridge client abstraction. The default implementation is mock-only and does not require this aggregate ROS2 node.

This package is a minimal skeleton for a future single-entry bridge. It exists to reserve the boundary without blocking the MVP mock Runtime path.
