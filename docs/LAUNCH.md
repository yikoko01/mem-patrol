# Launch / sharing kit

The project is young (created 2026-10-21). Facts as of 2026-10-24: 1 star, 0 forks,
0 open issues; the first Discussion is live. Use concrete artifacts, not "please star".

## One-paragraph pitch

MemPatrol is a dependency-free kernel for long-lived agents: it audits a SQLite memory
store (orphans, decay/consolidation, intents, config drift), scores prompt-ready recall
with anchor/instruction separation, and gates conversation with a judge-first,
lightly-throttled policy. It ships a CLI, a read-only MCP server and any-schema mapping.
Lexical is the default; vector is an optional provider seam.

## Hacker News (Show HN)

**Title:** Show HN: MemPatrol – memory patrol, recall and talk gates for long-lived agents

**Body:** We kept rebuilding the same three pieces around a SQLite memory store: hygiene
(orphans/decay/intents/config drift), recall that is safe to inject, and a decision about
whether the bot should speak. MemPatrol extracts them as deterministic Python kernels with
CLI + MCP. No host lock-in, no runtime deps (jieba optional), read-only by default; writes
need `--apply` + snapshot. The vector provider is a seam, not a bundled model — we would
rather show an honest lexical baseline. Feedback on the gate policy and schema mapping is
especially welcome.

## V2EX / 知乎 (Chinese)

**标题：** 把「记忆巡检 + 召回 + 该不该接话」抽成一个零依赖内核

**正文：** 长期 agent 的记忆问题往往不是“存不下”，而是：库里有没有孤儿/该衰减的/过期意图？
这一轮该注入什么、为什么？现在该不该说话、有没有节流？MemPatrol 把这三件事做成确定性
Python 内核：SQLite 任意 schema 映射、默认只读、`--apply` 先快照、CLI + 只读 MCP。
召回默认 lexical，vector 只留 provider 接口，不吹语义。欢迎拿自己的库结构来试，也欢迎
指出 gate 策略的问题。

## Demo assets

- `docs/demo.gif` — 32s terminal demo (synthetic data)
- `docs/ARCHITECTURE.md` — diagrams
- `docs/END-TO-END.md` — chat interjection + repair walkthrough
- `docs/COMPARISON.md` — MemGPT/Mem0/RAG positioning (honest)

## Promotion checklist

- [ ] Pin the welcome Discussion
- [ ] Create 2–3 `good first issue`s
- [ ] Post Show HN after a demo GIF is visible in README
- [ ] Post a Chinese write-up with real, de-identified use case
- [ ] Ask for schema shapes rather than stars
