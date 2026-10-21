# FAQ

## Does it require a specific host?

No. MemPatrol is a set of host-agnostic kernels for long-lived agents: SQLite
memory patrol/recall, conversation gates, metrics/eval, and a read-only MCP
server. It does not import or require an IM framework. Point `--db` at your
database and map its tables with `--schema` (or use `--schema auto`).

## License

**MIT** for 0.2.2 and later. Earlier releases (0.2.0/0.2.1) were Apache-2.0.
MIT is short and permissive; it has no explicit patent grant, so if patent
protection matters, Apache-2.0 may be preferable for future contributions.
This is not legal advice.
