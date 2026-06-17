# Tool Management

Tool v1 supports:

- in-memory registration for existing runtime tools
- manifest-based dynamic loading from a configured `tool_root`
- conflict-map based execution exclusion
- disabled-by-default MCP server shell
- hard denial for robot, arm, gripper, perception, ROS2, Nav2, MoveIt, and direct velocity-command backdoors

Robot capabilities are never generic tools; they stay in the SkillExecutor and bridge safety chain.
