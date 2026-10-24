# Tester guide (20–30 minutes)

Thank you for testing **MemPatrol 0.3.7**. You do **not** need to know the codebase. We need
honest feedback on installation, diagnosis, recall and whether the output is actionable.

## Safety first

- **Never point it at a production database.** Make a copy first:
  `sqlite3 /path/prod.db ".backup '/tmp/memcopy.db'"` (or `cp` while the app is idle).
- **Do not run `--apply`.** Test commands below are read-only.
- Do not send memory text, user ids, or tokens. If a DB can't be parsed, send only the
  output of `sqlite3 db ".schema"` (table/column names, no rows).
- Synthetic demo data is fine; there is one in this kit.

## Path A — try the bundled demo (no DB needed)

```bash
python -m pip install mem-patrol==0.3.7
# Android/proot/FAT: UV_LINK_MODE=copy uv pip install mem-patrol==0.3.7
cd tester-kit
PYTHON=python3 bash check.sh
```

Or manually:

```bash
memorix --version
memorix doctor
# CI can use: memorix doctor --strict  (exit 1 for stale dist-info warnings)
memorix diagnose --db demo.db --now 1792000100
memorix recall --db demo.db --user-id demo-user --query "8-23 比 8-19 更难"
python -m memorix.eval --suite all
```

Expected: version prints `mem-patrol 0.3.7`; diagnosis shows `total=12` and findings; recall
returns a memory block; eval is 24/24.

## Path B — your own SQLite DB (the useful test)

1. Make a copy (see safety).
2. Try auto-detection:
   ```bash
   memorix diagnose --db /tmp/memcopy.db --schema auto
   ```
   If it fails, map your tables explicitly:
   ```bash
   memorix diagnose --db /tmp/memcopy.db --schema /path/to/schema.json
   ```
   Minimal mapping (edit table/column names):
   ```json
   {"memories":{"table":"your_memories","id":"id","content":"text",
     "type":"kind","importance":"weight","created_at":"created_at"}}
   ```
3. Recall with a real question you would ask the agent:
   ```bash
   memorix recall --db /tmp/memcopy.db --query "your question" --user-id optional
   ```
4. Optional MCP (Claude Desktop / Cursor):
   ```json
   {"mcpServers":{"memorix":{"command":"memorix-mcp",
     "args":["--profile","both","--db","/tmp/memcopy.db"]}}}
   ```
   Then check the tool list includes `memorix_diagnose`, `memorix_recall`, etc.

## If `doctor` reports stale dist-info

A failed upgrade can leave `mem_patrol-<old>.dist-info` without `RECORD`. `doctor` now lists
all matching dist-info records and warns; remove the stale one (or reinstall with
`UV_LINK_MODE=copy`). It also checks the scripts next to `sys.executable`, so metadata alone
cannot make it claim "not installed".

## One-shot probe for your own DB

After copying your DB (never production), run:

```bash
python integration_check.py --db /tmp/memcopy.db --schema auto \
  --user-id your_id --query "your real question"
```

It only runs `--version`, `doctor`, `diagnose`, `recall`; no `--apply`. If `auto` fails,
send only `sqlite3 /tmp/memcopy.db ".schema"` (no rows).

## `doctor`: ok vs clean

- `ok: true` = package can run (imports/entrypoints/DB).
- `clean: true` = no warnings; stale dist-info/symlink makes `clean: false` while `ok` stays true.
- CI should use `memorix doctor --strict` (exit 1 on warnings) or read `clean`, not only `ok`.

## What we want to know

Please answer in your own words; “this is confusing” is useful.

1. Install: did `pip install mem-patrol==0.3.7` and `memorix --version` work? OS/Python?
2. Diagnosis: did it find anything **actionable**? Which finding was useful/noisy?
3. Schema: did `--schema auto` work? If not, what did the error say?
4. Recall: did it return the right memory? Did it inject an **irrelevant contract/preference**
   or return `(empty)` when you expected something?
5. MCP: did the server start and list tools? Which client?
6. Would you use it? What is the one missing thing (vector, UI, adapter, docs, speed…)?
7. Bugs: exact command + error traceback + minimal synthetic repro (no production data).

## Feedback template

```text
Environment: OS / Python / install method
Path: A demo / B own DB (schema table count only)
Install friction (1-5):
Diagnosis: useful findings? noisy?
Schema auto: worked? error?
Recall: right memory? irrelevant injection? empty?
MCP: not tried / worked / error
Top 1 confusing thing:
Top 1 missing feature:
Bug (command + traceback):
```

Send screenshots of terminal output if easier; redact paths/user ids.

## Lexical boundary (expected)

`喜欢喝冰美式` → `咖啡` and `想学吉他` → `音乐` return `(empty)` on lexical; synonyms
need the optional vector provider. Not a bug.

## Known limits (so you don't report them as surprises)

- Lexical recall is the default; **no bundled embedding model**.
- No chat UI/IM adapter; MCP/CLI only.
- Real-corpus historical replay has one documented data gap; current replay is 6/6.
- Large-scale (>100K) retrieval needs an ANN/vector layer; SQLite stays source of truth.
