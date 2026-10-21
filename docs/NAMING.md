# Naming & copy (bilingual)

## Decision

- **Project / repo / brand**: `MemPatrol` (`mem-patrol`)
- **PyPI distribution**: `mem-patrol`
- **Import package / existing CLI**: `memorix` (kept for compatibility)
- **CLI aliases**: `memorix`, `memorix-mcp`, `mem-patrol`, `mem-patrol-mcp`
- **Chinese positioning**: 记忆巡检 · 召回打分 · 接话闸门

> `memorix` is already taken on PyPI and by AVIDS2/memorix on GitHub; do not publish under it.

## GitHub About (paste, ≤350 chars)

Memory patrol + lexical recall + conversation gates for long-lived agents. Auditable SQLite kernels, CLI + MCP, zero runtime deps. 记忆巡检、召回打分与群聊接话决策内核；可审计、零依赖。

## One-liners

**EN**: Memory patrol, recall, and conversation gates for long-lived agents — dependency-free Python with CLI + MCP.

**ZH**: 给长期运行 agent 的记忆巡检、召回与接话闸门——零依赖 Python，带 CLI + MCP。

## Short

EN: Auditable memory hygiene, recall and talk gates for long-lived agents.
ZH: 给长期 agent 的可审计记忆巡检、召回与接话闸门。

## Medium

EN: Dependency-free Python kernels for SQLite memory patrol, anchor-aware recall and group-chat interjection decisions. Ships a read-only MCP server.
ZH: 零依赖 Python：SQLite 记忆巡检、锚点召回、群聊接话决策；附带只读 MCP server。

## Long (README / PyPI intro)

EN: MemPatrol is extracted from a running memory-patrol and group-chat judge. It audits SQLite memory stores (orphans, decay/consolidation, intents, config drift), scores prompt-ready recall with anchor and instruction separation, and gates interjection with a judge-first, lightly-throttled policy. It ships a read-only MCP stdio server and adapts to foreign tables through schema mapping.

ZH: MemPatrol 从运行中的记忆巡检与群聊裁判抽离而来：审计 SQLite 记忆库（孤儿、衰减/巩固、意图、配置漂移），做锚点感知、指令不参与匹配的召回打分，并用“裁判优先 + 轻节流”的闸门决定群聊接话；附带只读 MCP stdio server，支持自定义表结构映射。

## Release title

EN: v0.2.2 — Memory patrol, recall & conversation gates
ZH: v0.2.2 — 记忆巡检、召回与接话闸门

## Topics

llm-agents · memory · memory-management · mcp · model-context-protocol · chatbot · sqlite · retrieval · python · group-chat

## Install / run

```bash
pip install mem-patrol
memorix --version        # import/CLI name
mem-patrol --version     # alias
```
