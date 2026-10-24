# Contributing

Thanks for helping. MemPatrol is intentionally small: pure Python kernels, a SQLite
adapter, CLI and a read-only MCP server.

## Setup

```bash
git clone https://github.com/yikoko01/mem-patrol.git
cd mem-patrol
python -m venv .venv && . .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -p no:cacheprovider
```

## Before opening a PR

- `python -m pytest -p no:cacheprovider` — all tests pass.
- `python -m memorix.eval --suite all --baseline eval/baseline.json` — no regressions.
- `python -m memorix.retrieval.bench` and `python -m memorix.gatekeep.bench` — 6/6 and 9/9.
- If you change the recall scorer, run the real-corpus check with a local snapshot
  (`docs/REAL-CORPUS.md`) if available, or explain why not.

## Rules

1. **No host-specific imports** (IM SDKs / framework types) in `src/`. Adapters stay outside.
2. **Read-only by default**; any write path needs `--apply` and a backup/snapshot.
3. **Safety invariants are not configurable**: MCP read-only, apply-with-backup,
   instruction never ranks, contracts need an anchor.
4. **Keep the synthetic eval green**; add a case when fixing a recall/judge bug.
5. **No secrets or production data** in the repo; use hashes/manifests.
6. **Tests are part of the change**; small focused tests are preferred.

## Issues

Use the templates for bugs/features. Good first issues are labeled
`good first issue`; docs/benchmark work is labeled `docs` / `benchmarks`.

## Commit style

`type: short summary` (e.g. `fix: handle future timestamps`, `docs: split README`).
Keep changes reviewable; update `CHANGELOG.md` for user-visible changes.

## Versioning (pre-1.0)

We use SemVer-style tags while pre-1.0:

- patch: bug/docs/test fix with no new behavior;
- minor: new feature (e.g. 0.3.0 provider abstraction, 0.3.2 CLI `recall`);
- major: only after 1.0 or for a real breaking change; any break must be called out
  explicitly in `CHANGELOG.md`.

Do not infer a breaking change from a 0.x minor alone.

## Security

Do not paste production memory content, user ids, or API tokens into issues/PRs.
Report sensitive issues privately to the maintainer.
