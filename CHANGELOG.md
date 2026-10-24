# Changelog

All notable changes to this project. The kernels are extracted read-only from the
production AstrBot patrol/private-companion systems; production code is untouched.

## [0.3.3] - 2026-10-24

### Changed
- PyPI discovery metadata: richer keywords + Beta/Developer/AI/Database/library classifiers.
- Demo GIF moved to the top of both READMEs (centered) and now shows `memorix recall`.
- Scaling benchmark visualization (`docs/benchmarks.svg`), community guide and first
  GitHub Discussion; SemVer policy documented in CONTRIBUTING.

## [0.3.2] - 2026-10-24

### Added
- CLI `memorix recall --db ... --query ... [--user-id ...]` with `--json`
  (`memory_ids` + prompt-ready `text`).
- Claude Desktop / Cursor MCP config examples; GitHub Discussions enabled;
  community docs; real-corpus data-gap explanation; explicit vector win condition.

## [0.3.1] - 2026-10-24

### Fixed
- Provider test embedder no longer relies on randomized built-in `hash()`; CI
  is deterministic on Python 3.10/3.11/3.12.

## [0.3.0] - 2026-10-24

### Added
- Pluggable recall providers: `LexicalProvider` (default) and optional
  `VectorProvider` with a caller-supplied batch embedder; optional ONNX adapter
  (`mem-patrol[vector]`). No embedding model is bundled; lexical stays default.
- 30-second terminal demo (`docs/demo.gif`) generated from real CLI output on
  synthetic data.

## Versioning note

Pre-1.0: `0.2.3 → 0.3.0` was a **minor feature** (provider abstraction/vector seam),
not a breaking rewrite; `0.3.1` was a CI/test fix. `0.3.2` adds the CLI `recall` command
and docs/community material. Breaking changes, if any, get an explicit note.

## [0.2.4] - 2026-10-24

### Changed
- English-first `README.md` + separate `README.zh.md`; architecture, end-to-end,
  benchmarks, comparison and vector-provider design docs; contribution templates
  and roadmap; 10K/50K scaling benchmark; license rationale.

## [0.2.3] - 2026-10-22

### Added
- Privacy-preserving **real-corpus regression**: `eval/real_corpus.json`
  (snapshot SHA-256 + queries + expected ids + content hashes; no production text)
  and `python -m memorix.eval.real_corpus`.
- PyPI trusted-publishing workflow (`publish.yml`, manual dispatch).

## [0.2.2] - 2026-10-22

### Changed
- License changed from Apache-2.0 to **MIT** (more permissive).
- Docs de-emphasize the AstrBot origin: host-agnostic positioning, generic
  quickstart/tests, and a dedicated FAQ. AstrBot remains only a compatibility
  example, not a dependency.

## [0.2.1] - 2026-10-22

### Fixed
- Python 3.10 CI: `tests/test_packaging.py` falls back to `tomli`
  (`tomllib` is 3.11+); test extra installs `tomli` on <3.11.

## [0.2.0] - 2026-10-21

First installable release (M0–M4).

### Added
- **memorix (M0–M1)**: pure policies (orphan gate, sender labels, audit snapshot,
  decay/consolidation planning, intent expiry, finish gate), SQLite storage
  adapter (read-only by default), path-parameterized diagnose/repair CLI.
- **retrieval (M1.5)**: dependency-free lexical recall scorer with optional
  jieba anchoring, point-in-time replay, query/instruction separation and the
  guide §10.3 six-case bench (6/6).
- **gatekeep (M2)**: host-agnostic decision kernel (`Context` → `Decision`
  `{allow,text,reason,needs_tools}`), composable gates, directed fast path,
  needs-tools handoff/tool_task routing, shadow precision bookkeeping,
  pure reviewers and a 9-case judge replay set.
- **observability (M3)**: structured metric events, percentile/cost/reason
  aggregation, dependency-free SVG/HTML reports and a JSONL report CLI.
- **eval (M3)**: offline replay suites (recall/judge/policy) with JSON reports
  and baseline regression (`--update-baseline` refuses red reports).
- **safety (M3)**: unified `<untrusted>` wrapper (control chars, tag breakout,
  source whitelist, truncation).
- **MCP server (M4)**: zero-dependency stdio MCP server
  (`memorix-mcp`) exposing six read-only tools; supports protocol versions
  2025-06-18 / 2025-03-26 / 2024-11-05.
- **Packaging (M4)**: Apache-2.0 LICENSE, wheels/sdist, console scripts,
  GitHub Actions CI + tag release workflow.

### Fixed
- Python 3.10 CI: `tests/test_packaging.py` now falls back to `tomli`
  (`tomllib` is 3.11+); test extra installs `tomli` on <3.11.

### Changed (M4.5)
- Distribution/repo name is now **`mem-patrol`** (import package and existing CLI remain
  `memorix`; aliases `mem-patrol`/`mem-patrol-mcp` added). Avoids the taken
  `memorix` PyPI/GitHub name; bilingual copy in `docs/NAMING.md`.

### Added (M4.3)
- Production handoff schema form (`tables/columns`) with `unit` (ms/s),
  `exclude` (archived) and private-chat rule (`group_id == sender_id`);
  `recent_private_context()`; example `examples/astrbot-self-learning.schema.json`
  verified on a read-only AstrBot snapshot (1254 memories / 4079 raw / 6173 bot).

### Added (M4.2)
- Configurable SQL schema mapping / auto-detection (`--schema native|auto|JSON`,
  `MEMORIX_SCHEMA`, MCP `schema` arg): only a memories table is required;
  message-dependent features fail with a clear `SchemaError`.

### Added (M4.1)
- Use-case presets `chat` / `project` / `both` (`memorix.profiles`) with an MCP
  tool allow-list (`memorix-mcp --profile ...`), CLI `memorix profile`, a switch
  matrix (`docs/USE-CASES.md`) and a copy-ready two-mode README sample.

### Notes
- Runtime has **no third-party dependencies**; `jieba` is an optional anchor
  extra (`pip install -e '.[anchor]'`), pytest+jieba for tests (`.[test]`).
- All tools are read-only. Repair commands stay in the CLI behind `--apply`
  (with automatic database snapshots).
