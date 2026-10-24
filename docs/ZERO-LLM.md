# Zero-LLM paths

MemPatrol separates deterministic kernels from the optional model call.

## Runs without any model

- `memorix diagnose|orphan|status|audit|intents|decay|finish|consolidate|recall|profile`
- `memorix.eval` (recall/judge/policy replay), `memorix.retrieval.bench`, `memorix.gatekeep.bench`
- all MCP tools (read-only): diagnose/orphan/recall/gate_check/judge_replay/eval
- `decide(ctx)` with **no judge**: hard gates only, action `candidate` if they pass

```python
from memorix.gatekeep import Context, decide

outcome = decide(Context(text="这个怎么弄？", config={"enable_group_interjection": True, "group_interject_max_daily": 30}))
assert outcome.action in {"dropped", "candidate"}
```

`candidate` means "the deterministic gates did not veto; a host/LLM may decide". It is not a
message to send.

## Optional judge

Only the final speak/no-speak call needs an injected judge:

```python
def judge(ctx) -> dict:
    return {"should_reply": True, "text": "接一句", "needs_tools": False}

outcome = decide(ctx, judge=judge)   # sent / handoff / tool_task / dropped
```

A stub judge is useful for tests and offline demos; it does not make the gate semantic.
Production quality depends on your judge/model and is measured by the eval/replay gates,
not by the deterministic core.
