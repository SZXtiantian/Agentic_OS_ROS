# hello_world_agent Prompt

Use only Agentic OS high-level SDK APIs. This app demonstrates context,
memory, storage, tool, skill, and report calls from the copied app template.

Natural-language planning must use the Agentic OS system LLM facade. Return one
raw JSON object with `schema_version`, `planner_mode: llm`, `greeting`,
`report_message`, `memory_key`, `storage_path`, `tool_args`, and
`user_summary`. The app performs deterministic validation before execution.
