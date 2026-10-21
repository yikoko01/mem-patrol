"""Read-only ledger helpers (the append contract stays with the agent/LLM)."""
from __future__ import annotations

import os
from pathlib import Path


def read_text(path: str | Path | None) -> str | None:
    """Return the ledger text, or None when the file is missing/unreadable."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return None


def last_mark(text: str | None) -> str | None:
    """Last ``### `` heading in the ledger (used by finish --from-orphan)."""
    if not text:
        return None
    newest = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            newest = stripped[4:].strip()
    return newest


def mtime(path: str | Path | None) -> float:
    if not path:
        return 0.0
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
