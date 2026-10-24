# Community

- **Discussions**: https://github.com/yikoko01/mem-patrol/discussions
- **Issues**: bug reports / feature requests via the templates.
- **Contributing**: [`CONTRIBUTING.md`](../CONTRIBUTING.md); start with `good first issue`.

## Welcome thread

A pinned "Welcome / Introduction" post covers:

1. what MemPatrol is (patrol + recall + conversation gate, not a full memory layer);
2. design philosophy (deterministic by default, judge-first, auditable, no host lock-in);
3. current limits (lexical default, vector provider needs your model, real corpus is private);
4. how to share a use case: DB shape, constraints, what you tried, expected vs actual.

## Blog post ideas

- *Why Judge-First Interjection beats "reply probability"*: hard gates only remove the
  obvious "not now"; the judge decides whether a natural insertion point exists.
- *Memory Patrol as a Kernel*: why orphan/decay/finish gates are deterministic steps,
  not an LLM loop.
- *Auditing a Memory Store*: read-only first, `--apply` with snapshots, and a real-corpus
  replay instead of hand-waving quality.

## First issues

Good starting points: docs examples, benchmark visualizations, MCP client recipes,
additional schemas, and tests for edge cases. Do not include production memory text or
tokens in any issue/discussion.
