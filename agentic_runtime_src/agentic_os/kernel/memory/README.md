# Memory Management

Memory v1 follows the AIOS manager/provider shape:

- `MemoryNote` carries semantic metadata and robot-specific metadata.
- `InMemoryMemoryProvider` is the RAM tier.
- `MemoryManager` can evict old RAM notes into a persistent provider.
- `LexicalMemoryRetriever` is the default no-dependency retrieval path.
- `ContextInjector` and `ConversationExtractor` provide the LLM memory hooks.

Vector databases and embedding providers are optional future backends and are not imported at module load time.
