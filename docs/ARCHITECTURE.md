# Architecture

MemPatrol is deliberately split into small layers so a host adapter can reuse one
piece without the rest.

```mermaid
flowchart TB
  subgraph Data
    DB[(SQLite)]
    SCHEMA[schema.py<br/>native / auto / JSON mapping]
  end
  subgraph M0["M0 · policy (pure)"]
    P1[orphan / sender labels]
    P2[audit snapshot / finish gate]
    P3[decay / consolidation / intents]
  end
  subgraph M1["M1 · store + CLI"]
    S[SQLiteStore]
    CLI[memorix CLI]
  end
  subgraph M15["M1.5 · recall"]
    R1[anchor / tokens]
    R2[scorer + coverage floor]
  end
  subgraph M2["M2 · gatekeep"]
    G1[hard gates]
    G2[judge contract / needs_tools]
  end
  subgraph M3["M3 · observability/eval/safety"]
    O1[metrics + SVG/HTML]
    O2[synthetic + real-corpus eval]
    O3[untrusted wrapper]
  end
  subgraph M4["M4 · MCP"]
    MCP[stdio server / 6 read-only tools]
  end
  DB --> SCHEMA --> S
  S --> P1 & P2 & P3
  S --> CLI --> MCP
  S --> R1 --> R2 --> MCP
  R2 --> G1 --> G2
  G2 --> MCP
  R2 --> O1
  P1 & P2 & P3 --> O2
```

## Data flow

### Patrol / long-term project

```mermaid
sequenceDiagram
  participant Operator
  participant CLI
  participant Store
  participant Policy
  Operator->>CLI: memorix diagnose --db ...
  CLI->>Store: read-only SELECTs
  Store->>Policy: MemoryRecord[]
  Policy-->>CLI: findings / plans (no writes)
  Operator->>CLI: decay --apply
  CLI->>Store: snapshot DB
  CLI->>Store: single transaction (rollback on mismatch)
```

### Recall

```mermaid
sequenceDiagram
  participant Chat as Chat host
  participant Recall
  participant Store
  Chat->>Store: load non-archived rows (as-of optional)
  Chat->>Recall: query + private context + user id
  Recall->>Recall: anchor nouns -> candidates -> coverage floor
  Recall-->>Chat: prompt-ready block (or empty)
```

### Interjection

```mermaid
sequenceDiagram
  participant Host
  participant Gates
  participant Judge as LLM judge
  Host->>Gates: Context(text, directed, config)
  Gates-->>Host: dropped (hard gate) or pass
  Gates->>Judge: pass -> judge call
  Judge-->>Gates: {should_reply, text, needs_tools}
  Gates-->>Host: sent / handoff / tool_task / dropped
```

## Modules

| Path | Responsibility |
|---|---|
| `policy/` | pure M0 functions: orphan, sender labels, audit, finish, decay, consolidation, intents |
| `store.py` | SQLite adapter + schema mapping; read-only unless `readonly=False` |
| `cli.py` | diagnose/plan/apply commands; `--apply` is the only write entry |
| `retrieval/` | anchor selection, lexical scorer, private context, §10.3 benches |
| `gatekeep/` | gates, judge JSON contract, needs_tools routing, shadow/reviewers |
| `observability/` | metrics + zero-dep SVG/HTML report |
| `eval/` | synthetic suites + baseline + privacy-preserving real-corpus check |
| `safety/` | untrusted text wrapper (structure, not semantic filtering) |
| `mcp/` | JSON-RPC 2.0 stdio server; tools are read-only |
| `profiles.py` | chat/project/both presets (defaults, not locks) |

## Invariants

1. **No writes without `--apply`**, and `--apply` snapshots first.
2. MCP has no write tool; repair stays in the CLI.
3. `query` and `instruction` are separate; instruction text never ranks.
4. Contract/preference memories are not injected without an anchor hit.
5. `archived` is excluded from recall, not from diagnosis counts.
6. A schema without message tables still supports memory-only features and fails
   message features with a clear `SchemaError`.
