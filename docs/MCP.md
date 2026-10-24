# MCP server (M4)

`memorix-mcp` is a **zero-dependency** stdio MCP server (JSON-RPC 2.0,
newline-delimited). It exposes the kernels as **read-only** tools; repair
operations stay in the CLI behind `--apply`.

## Protocol

- Supported versions: `2025-06-18`, `2025-03-26`, `2024-11-05`.
- The server echoes the client's requested version when supported, otherwise
  replies with `2025-06-18`.
- Methods: `initialize`, `ping`, `tools/list`, `tools/call`, plus
  `notifications/initialized` (no response).
- Errors: `-32700` parse, `-32600` invalid request, `-32601` unknown method,
  `-32603` internal; tool failures use `result.isError=true` with text content.

## Tools

| Tool | Args | Returns |
|---|---|---|
| `memorix_diagnose` | `db`, optional `schema`, `state`, `ledger`, `audit_snapshot`, `config[]`, `now` | `MEMORIX_DIAGNOSIS …` text (findings) |
| `memorix_orphan` | `db`, optional `schema`, `state` | `ORPHAN_NONE` / `ORPHAN n: …` |
| `memorix_recall` | `db`, `query`, optional `schema`, `context`, `group_id`, `user_id`, `top_k`, `max_chars`, `as_of_ms` | prompt-ready memory block or `(empty)` |
| `memorix_gate_check` | `text`, optional `group_id`, `directed`, `scene_trigger`, `config` | `ACTION=… REASON=…` + per-gate trace (no LLM) |
| `memorix_judge_replay` | — | `JUDGE_REPLAY 9/9` |
| `memorix_eval` | optional `suite` = `all`/`recall`/`judge`/`policy` | `EVAL n/n` + per-suite lines |

Recall `top_k` is clamped to 1..10 and `max_chars` to 240..1800. All tools are
**read-only**: none takes a write flag. `query` for recall is the
user's own words (the instruction text must not be used as the query — guide
§10.3 case 6).

## Profiles (tool allow-list)

`memorix-mcp --profile chat|project|both` (default `both`) filters `tools/list` and rejects calls outside the profile:

| profile | tools |
|---|---|
| `chat` | recall, gate_check, judge_replay |
| `project` | diagnose, orphan, recall, eval |
| `both` | all 6 |

## Client config

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{"mcpServers":{"memorix":{"command":"memorix-mcp","args":["--profile","both","--db","/absolute/path/messages.db"]}}}
```

### Cursor

`.cursor/mcp.json` uses the same shape:

```json
{"mcpServers":{"memorix":{"command":"memorix-mcp","args":["--profile","chat","--db","/absolute/path/messages.db"]}}}
```

Use absolute DB paths; the server is stdio-only and read-only.

```json
{
  "mcpServers": {
    "memorix": {
      "command": "memorix-mcp",
      "args": ["--profile", "project", "--db", "/path/to/messages.db"]
    }
  }
}
```

`--db` is a default; each DB-taking tool also accepts an explicit `db`
argument. The server also honors `MEMORIX_DB` when `--db` is omitted.
For foreign databases pass `schema` = `auto` / a JSON file / inline JSON mapping
(see `docs/SCHEMA.md`); only a memories table is required.

## Smoke test

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | memorix-mcp
```

## Security boundary

- stdio only; no network listener, no auth layer (the host process owns trust).
- Tools never write; they do read arbitrary DB paths supplied by the caller
  (same trust level as the CLI).
- Returned memory text is untrusted data; hosts must wrap it with
  `memorix.safety.wrap_untrusted` before putting it into a prompt.
