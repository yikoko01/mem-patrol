# Foreign-schema integration matrix

This is the "will it work on someone else's DB?" test layer. It is **read-only**;
never point it at production.

## Covered in CI (`tests/test_integration_schemas.py`)

| scenario | what is verified |
|---|---|
| SQLAlchemy-style names/columns | `auto` finds `long_term_memory(id, body, kind, weight, created, ...)`; no autoincrement needed |
| custom raw/bot tables | `chat_messages` / `bot_replies` mapping; `max_message_ids`, sender names |
| archived rows | excluded from recall, still counted by diagnose |
| private/group | `group_id == sender_id` only for private context |
| memory-only schema | diagnose/recall work; `status` fails with a clear SchemaError (exit 4) |
| CLI | `diagnose` / `recall --json` with inline mapping |
| MCP | `memorix_diagnose` / `memorix_recall` with `schema: "auto"` |
| diagnosis | foreign rows produce a normal report |

## Run against a user DB (copy first)

```bash
# 1) safe copy
sqlite3 production.db ".backup '/tmp/memcopy.db'"

# 2) read-only integration probe
python scripts/integration_check.py --db /tmp/memcopy.db --schema auto \
  --user-id <id> --query "your real question"

# 3) if auto fails, send only the schema (no rows) and build a mapping
sqlite3 /tmp/memcopy.db ".schema"
```

The script only calls `--version`, `doctor`, `diagnose`, `recall`; it has no `--apply`
path and writes nothing. Failures print a short last-line summary; use `--verbose`
for full command output.

## Production snapshot check (maintainers, private data stays local)

```bash
python scripts/integration_check.py \
  --db /tmp/memcopy.db \
  --schema examples/self-learning.schema.json \
  --user-id <id> \
  --query "8-23 比 8-19 更难"
```

Latest local run on a 1,254-memory snapshot: `total=1254`, recall rows
exclude archived (1,238), private context filtered, `INTEGRATION_PASS`.
