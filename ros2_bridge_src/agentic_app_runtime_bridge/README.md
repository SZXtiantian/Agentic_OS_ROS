# agentic_app_runtime_bridge

Runtime calls the world, safety, and capability bridge contracts through the Agentic Runtime bridge client abstraction. Production deployments must connect those contracts to real ROS2 services, actions, or topics owned by AgenticOS bridge packages.

This package is a minimal skeleton for a future single-entry aggregate bridge. It reserves the boundary without providing a simulated success path; missing ROS2 dependencies must surface stable bridge/backend error codes through the concrete capability bridge nodes.
