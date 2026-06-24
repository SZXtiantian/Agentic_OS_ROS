# Agentic SDK

Installed mapping for Agentic SDK architecture modules. The foundation-complete
Python SDK implementation lives in `agentic_runtime.sdk`.

Agent Apps use high-level SDK calls only. They must not import ROS2 client
libraries, publish direct velocity commands, subscribe to low-level robot state
topics directly, or call Nav2 or MoveIt actions directly. Provider/mode availability comes from
`KernelService.status()["providers"]`; reserved capabilities return stable
errors rather than successful placeholder responses.
