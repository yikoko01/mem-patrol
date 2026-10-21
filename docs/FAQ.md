# FAQ

## Is this AstrBot-specific?

**No.** There is no `astrbot` import and no AstrBot runtime dependency. The package is a
host-agnostic set of kernels (policy, recall, gatekeep, metrics, eval, MCP). AstrBot appears
in the docs for two reasons only:

1. **Provenance** — the kernels were extracted read-only from a running AstrBot deployment
   (see `docs/M0.md` and the milestone reports).
2. **Compatibility example** — the default SQLite schema is a three-table layout that
   originated there, and `examples/astrbot-self-learning.schema.json` documents one real
   handoff. Any other SQLite schema can be used via `--schema` / `schema` (see
   `docs/SCHEMA.md`).

If you use it elsewhere: point `--db` at your database, provide a `schema.json` (or
`--schema auto`), and use the MCP/CLI interfaces. No AstrBot installation is required.

## Why are there milestone reports named M0–M4 with AstrBot paths?

They are historical engineering records from the extraction, kept for auditability. They are
not required reading to use the package; `README.md` and `docs/USE-CASES.md` are the
current, host-neutral entry points.

## License

**MIT** for 0.2.2 and later. Earlier releases (0.2.0/0.2.1) were Apache-2.0. MIT is shorter and
more permissive; it has no explicit patent grant, so if patent protection matters to you,
Apache-2.0 may be preferable for future contributions. This is not legal advice.
