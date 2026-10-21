# MemPatrol · 记忆巡检、召回与接话闸门

[![PyPI](https://img.shields.io/pypi/v/mem-patrol.svg)](https://pypi.org/project/mem-patrol/)

> Memory patrol, lexical recall and conversation gates for long-lived agents.
> 给长期运行 agent 的记忆巡检、召回打分与群聊接话闸门。

Dependency-free kernels extracted from the *memory patrol* (记忆巡检) and
*group-chat judge* subsystems: orphan-batch gate, real sender labels,
config-audit snapshot diff, decay/consolidation planning, intent expiry, finish
gate, lexical recall scorer, composable decision gates, metrics, offline eval,
untrusted wrapper and an MCP stdio server.

M0–M4 are **host-agnostic kernels**: no IM framework or host import, no network. File IO lives
behind `memorix.adapters.files`; the CLI/store (M1), the recall scorer (M1.5)
and the gatekeep decision kernel (M2) build on the M0 pure policies.

## Install

> Distribution name is **`mem-patrol`**; the import package and CLI names stay **`memorix`** for compatibility.
> 发行包名是 **`mem-patrol`**，导入包/原 CLI 仍叫 **`memorix`**。

```bash
pip install mem-patrol                  # from PyPI (0.2.3+)
python -m pip install .                 # or from this checkout
python -m pip install '.[test]'         # pytest + jieba for the full suite
memorix --version                       # mem-patrol 0.2.3 (import/CLI name stays memorix)
mem-patrol --version                    # distribution alias, same CLI
```

For a local checkout, `PYTHONPATH=src` works without installing.

## Foreign databases (schema mapping)

Your tables do not need the default/legacy table names:

```bash
memorix diagnose --db my.db --schema schema.json   # explicit mapping
memorix diagnose --db my.db --schema auto          # auto-detect
MEMORIX_SCHEMA=schema.json memorix diagnose --db my.db
```

Only a memories table is required; message-dependent features (`status`/`finish`) return a
clear `SchemaError` when `raw_messages`/`bot_messages` are not mapped. MCP tools accept a
`schema` argument. A real-world schema example is included at
[examples/self-learning.schema.json](examples/self-learning.schema.json)
(ms/s units, `archived` exclusion, private-chat rule).
See [docs/SCHEMA.md](docs/SCHEMA.md).

## Use-case profiles (chat / project / both)

```bash
python -m memorix.profiles --list       # chat / project / both
python -m memorix.profiles --name chat
memorix profile --name project          # CLI view
```

`chat` = recall + gatekeep; `project` = patrol/diagnose/eval; `both` = all, **with judge-first interjection enabled and light throttle** (30/day, 10s consult, 1min speech interval). MCP accepts `--profile chat|project|both` and filters the read-only tool list. See [docs/USE-CASES.md](docs/USE-CASES.md) and the copy-ready [README-两用样稿.md](README-两用样稿.md).

## MCP server

```json
{
  "mcpServers": {
    "memorix": {"command": "memorix-mcp", "args": ["--profile", "both", "--db", "/path/to/messages.db"]}
  }
}
```

Zero-dependency stdio MCP server (`memorix-mcp` / alias `mem-patrol-mcp`) exposing six **read-only** tools
(diagnose / orphan / recall / gate_check / judge_replay / eval), negotiating
protocol `2025-06-18` / `2025-03-26` / `2024-11-05`. See `docs/MCP.md`.

## Run the tests (no install needed)

```bash
python -m pytest -p no:cacheprovider   # any Python >= 3.10 with pytest
```

`pyproject.toml` sets `pythonpath = ["src"]`, so the package is importable
without `pip install`. The full **368-test** run needs the optional `jieba` anchor extra
(`pip install '.[test]'`); without it the anchor-dependent tests are skipped
(`memorix.eval --suite all` still passes 24/24).

## Layout

```
src/memorix/policy/            pure policy functions (M0)
src/memorix/adapters/files.py  file IO (fingerprints/snapshots)
src/memorix/store.py, cli.py   SQLite adapter + diagnose/repair CLI (M1)
src/memorix/retrieval/         recall scorer + §10.3 replay bench (M1.5)
src/memorix/gatekeep/          decision kernel + judge replay set (M2)
src/memorix/observability/     metrics + zero-dep SVG/HTML report (M3)
src/memorix/eval/              replay suites + baseline regression (M3)
src/memorix/safety/            unified untrusted wrapper (M3)
src/memorix/mcp/               MCP stdio server + 6 read-only tools (M4)
src/memorix/profiles.py        chat / project / both presets (M4.1)
src/memorix/schema.py          foreign-DB schema mapping / auto-detect (M4.2)
eval/baseline.json             evaluation baseline (M3)
dist/                          built wheel/sdist (M4)
tests/                         pytest-native tests (368)
docs/                          M0–M4 reports + USE-CASES/MCP/README samples
LICENSE, CHANGELOG.md          MIT + release notes
```

## CLI (M1)

```bash
PYTHONPATH=src python -m memorix diagnose --db <path/to/messages.db>
```

All commands are **read-only by default**; writes require `--apply` and take a
database snapshot first. Paths are explicit (`--db/--state/--ledger/...`) or
`MEMORIX_*` env vars — nothing points at production by default. See
`docs/M1.md` for the full command table and `docs/DECISIONS.md` for the
approved design decisions.

## Recall scorer (M1.5)

```bash
PYTHONPATH=src python -m memorix.retrieval.bench
# RESULT 6/6 passed
```

Zero runtime dependencies; `jieba` is an optional anchor extra
(`pip install -e '.[anchor]'`). Lexical only for now; the `vector` provider is a
documented seam. `recall(query, ..., instruction=...)` never matches the
instruction text (the guide §10.3 case-6 rule).

## Gatekeep (M2)

```python
from memorix.gatekeep import Context, decide

ctx = Context(
    text="这个怎么弄？",
    config={"enable_group_interjection": True, "group_interject_max_daily": 10},
)
outcome = decide(ctx, judge=lambda _ctx: '{"should_reply": true, "text": "我看看"}')
assert outcome.action == "sent"
```

Host-agnostic: no IM types, no DB, no network. Gates, JSON contract,
needs-tools routing (`handoff`/`tool_task`), shadow precision bookkeeping and
two pure reviewers (bare promise / absence-without-retrieval). See
`docs/M2.md`.

## Metrics / eval / safety (M3)

```bash
PYTHONPATH=src python -m memorix.eval --suite all --baseline eval/baseline.json
PYTHONPATH=src python -m memorix.observability --input events.jsonl --out report.html
```

```python
from memorix.safety import wrap_untrusted
wrapped = wrap_untrusted(untrusted_text, source="group:g1")
```

Real-corpus regression (no stored text): `python -m memorix.eval.real_corpus --db <snapshot> --user-id <id> --manifest eval/real_corpus.json`. See `docs/REAL-CORPUS.md`.

See `docs/M3.md`. The milestones (M0–M4) stay dependency-free (no network, no
host imports); IO lives behind adapters/CLI. M4 adds the MCP server and
packaging — see `docs/M4.md`.

## License

**MIT**. See `LICENSE` (0.2.2+; earlier releases were Apache-2.0).

## Safety

M0 was extracted from a running production system **read-only**; this package never
writes the source system. See `docs/M0.md` for provenance.
