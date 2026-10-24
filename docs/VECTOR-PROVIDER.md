# Vector provider design (planned, 0.3.x)

Current state: **lexical only**. The `vector` provider is a documented seam, not an
implementation. Do not claim semantic recall today.

## Interface

```python
class BaseRecallProvider(Protocol):
    def recall(
        self,
        query: str,
        *,
        rows: Sequence[RetrievalRow],
        context: str = "",
        group_id: str = "",
        user_id: str = "",
        top_k: int = 5,
        instruction: str = "",
    ) -> str: ...
```

Implementations:

- `LexicalProvider` — current anchor/scorer (zero deps, default).
- `VectorProvider` — embeddings + similarity; optional dependency.

`recall()` stays the public API; callers do not branch on provider.

## Dependency isolation

- `memorix/retrieval/provider.py` — protocol + factory.
- `memorix/retrieval/vector/` — optional implementation (embedding client/ONNX).
- No vector/embedding import at package import time; optional extra
  (`pip install 'mem-patrol[vector]'`).
- Core tests must pass without the extra.

## Evaluation

The same §10.3 cases and the real-corpus manifest must run against both providers:

```bash
python -m memorix.eval --suite all --backend lexical
python -m memorix.eval --suite all --backend vector   # optional
```

Report per-case hits and latency; do not switch the default until vector wins on the
real corpus without regressions.

## Privacy / offline

- Prefer local ONNX or a self-hosted embedding endpoint for privacy-sensitive users.
- Never send memory text to a third party without explicit opt-in.
- Cache embeddings outside the SQLite memory DB; a rebuild must be possible.

## Pitfalls

- Embedding model/version drift breaks reproducibility: pin model + dimensions.
- Chunking long memories changes recall behavior; define a deterministic policy.
- Vector-only recall loses anchor/instruction invariants; keep those checks in a shared
  post-filter.
