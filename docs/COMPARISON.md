# Positioning and comparison

MemPatrol is not a drop-in replacement for a full memory framework; it is a small,
auditable kernel set plus an MCP surface. Compare by what you need.

| project / class | primary shape | strengths | trade-offs |
|---|---|---|---|
| **MemPatrol** | SQLite memory patrol + lexical recall + conversation gate | deterministic, read-only defaults, schema mapping, MCP, zero runtime deps | lexical only; no vector/RAG stack; small ecosystem |
| MemGPT-style | agent-managed paging / long context | flexible, research lineage | more moving parts; LLM decides memory operations |
| Mem0-style | extraction + vector memory layer | semantic recall, managed integrations | needs embedding/provider; less deterministic audit surface |
| plain RAG / vector DB | document retrieval | mature semantic search | no memory lifecycle, no interjection decision, no audit gates |

## What is different here

1. **Patrol is a first-class surface**: orphan detection, decay/consolidation plans,
   intent expiry, finish gates, config-drift audit — not just “store/retrieve”.
2. **The gate is separate from recall**: “what do I know” and “should I speak now” are
   different questions; the judge contract and hard gates are independent.
3. **Auditability**: read-only by default, `--apply` with snapshots, offline eval and
   real-corpus replay; no hidden writes.
4. **Portable deployment**: one Python package, SQLite, CLI + MCP; adapters only map
   rows/contexts.

## When to choose it

- You already have a SQLite memory store and want hygiene + recall + a speak/no-speak
  decision without adopting a whole agent framework.
- You need explicit, reproducible operations and an MCP surface for coding agents.

## When not to choose it

- You need semantic/vector recall today (the `vector` provider is a documented seam,
  not implemented yet).
- You want a hosted memory service with extraction pipelines and vendor integrations.
- You need a turnkey chat product; this is a kernel/CLI/MCP layer, not an IM UI.
