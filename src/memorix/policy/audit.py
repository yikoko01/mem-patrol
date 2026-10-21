"""Config-audit snapshot diff ("changed but not recorded in the ledger").

Production logic, preserved:
1. compare the content fingerprint (md5) with the last acknowledged snapshot;
   identical -> benign (mtime refreshed by the runtime), refresh silently;
2. content really changed -> is the file named in the ledger text?
   named -> acknowledged, refresh; not named -> AUDIT_ALERT and do **not**
   refresh, so it keeps alerting until a human records it.

File discovery, canonicalisation (``realpath``) and IO live in
:mod:`memorix.adapters.files`; this module only compares data. ``FileState.path``
must therefore be canonical — the adapter guarantees that.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

from ..models import AuditResult, FileChange, FileState

__all__ = ["AUDIT_MTIME_TOLERANCE", "ledger_mentions", "classify_audit"]

AUDIT_MTIME_TOLERANCE = 60  # seconds accepted between ledger mtime and file mtime


def ledger_mentions(ledger_text: str, path: str) -> bool:
    """True when the ledger text names the file (basename or full path)."""
    base = os.path.basename(path)
    return bool(base and (base in ledger_text or path in ledger_text))


def classify_audit(
    prev_snapshot: Mapping[str, str],
    files: Iterable[FileState],
    ledger_text: str | None,
    ledger_mtime: float,
    tolerance: float = AUDIT_MTIME_TOLERANCE,
) -> AuditResult:
    """Classify the monitored files against the acknowledged snapshot.

    ``ledger_text is None`` means the ledger file is missing: production aborts
    with AUDIT_ERROR before comparing/writing anything, so the snapshot is
    returned unchanged with ``ledger_missing=True``.
    """
    snapshot: dict[str, str] = dict(prev_snapshot)
    if ledger_text is None:
        return AuditResult(
            suspicious=(),
            benign=(),
            snapshot=snapshot,
            ledger_missing=True,
        )
    suspicious: list[FileChange] = []
    benign: list[FileChange] = []
    seen: set[str] = set()

    for state in files:
        real = state.path  # adapter guarantees a canonical realpath
        if real in seen:
            continue
        seen.add(real)

        if snapshot.get(real) == state.md5:
            # Content unchanged: a runtime mtime refresh is benign, not an alert.
            if state.mtime > ledger_mtime + tolerance:
                benign.append(FileChange(real, state.mtime, state.md5))
            snapshot[real] = state.md5
            continue

        # Content changed. Only an explicit ledger mention counts as acknowledged.
        if ledger_mentions(ledger_text, real):
            snapshot[real] = state.md5
            continue

        # Alert and keep the old fingerprint so the next run alerts again.
        suspicious.append(FileChange(real, state.mtime, state.md5))

    return AuditResult(
        suspicious=tuple(suspicious),
        benign=tuple(benign),
        snapshot=snapshot,
    )
