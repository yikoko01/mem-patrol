# End-to-end walkthrough

Two scenarios: a chat interjection and a project-memory repair. Outputs are illustrative
(the exact reply text comes from your judge/host).

## A. Chat: should the bot speak?

### 1. Load memories and recent private context

```python
from memorix.retrieval.context import recent_private_context
from memorix.retrieval.store import load_rows
from memorix.retrieval.score import recall

rows = load_rows("messages.db", schema="auto")
context = recent_private_context("messages.db", user_id, schema="auto", limit=4)
memory = recall(user_message, rows=rows, context=context, user_id=user_id, top_k=5)
```

`recall` returns an empty string when nothing clears the coverage floor; that is a
feature, not an error. When it returns text, it is ready to place in the prompt.

### 2. Run the hard gates + judge

```python
from memorix.gatekeep import Context, decide

ctx = Context(
    text=user_message,
    user_id=user_id,
    group_id=group_id,
    directed=is_directed,          # @/reply/name path
    config={
        "enable_group_interjection": True,
        "group_interject_max_daily": 30,
        "group_interject_judge_min_consult_seconds": 10,
        "group_interject_min_interval_minutes": 1,
    },
)
outcome = decide(ctx, judge=llm_judge)
```

| outcome.action | meaning |
|---|---|
| `sent` | use `outcome.text` |
| `handoff` | directed + needs tools: return control to the main agent |
| `tool_task` | non-directed + needs tools: queue a background tool task |
| `dropped` | hard gate or judge said no; `outcome.reason` explains |

### 3. What the judge sees

The judge receives the message, recent context, optional memory block, and the reply
contract. It returns JSON:

```json
{"should_reply": true, "text": "接一句", "needs_tools": false, "reason": "有自然插入点"}
```

If it returns `should_reply=false`, the turn is `dropped`; the reason is logged for
shadow/quality review. Throttles (daily cap, consult window, speech interval) are
checked before the judge and never turn into a silent permanent veto.

## B. Project: diagnose and repair memory

```bash
memorix diagnose --db messages.db --state last_patrol.json --json
# MEMORIX_DIAGNOSIS
# total=1254
# risk.high=0
# ... findings
```

Plan first:

```bash
memorix decay --db messages.db            # read-only plan
memorix decay --db messages.db --apply    # snapshot -> transaction
```

What `--apply` does:

1. copies the DB to `memorix-backups/` before writing;
2. applies only the validated rows, one transaction;
3. aborts on row-count mismatch, so concurrent edits cannot be silently overwritten.

`status`/`finish` need message tables; with a memory-only schema they return a clear
`SchemaError` rather than reading the wrong table.

## C. MCP

```json
{"mcpServers":{"memorix":{"command":"memorix-mcp","args":["--profile","both","--db","/path/messages.db"]}}}
```

Typical agent loop:

1. `memorix_recall` with the user's own words (`query`) and `user_id`;
2. pass the returned block to the model;
3. `memorix_gate_check` for an interjection decision (no LLM in that tool);
4. `memorix_diagnose`/`memorix_orphan` for maintenance.

All tools are read-only; writes stay in the CLI with `--apply`.
