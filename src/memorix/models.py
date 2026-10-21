"""M0 data contracts (pure data only, no IO).

The records mirror the shapes used by the production patrol script
(`/root/AstrBot/data/patrol/memory_patrol.py`, read-only reference), but they are
plain dataclasses so the kernel never has to import ``sqlite3``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def field_of(row: Any, key: str, default: Any = None) -> Any:
    """Read one field from a Mapping, a sqlite3.Row, or a dataclass record."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def as_int(value: Any, default: int = 0) -> int:
    """Best-effort int conversion (production data has mixed ``importance`` types)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class MemoryRecord:
    """One row of the production ``memories`` table (only the used columns)."""

    id: int
    memory_type: str = ""
    importance: Any = 0
    created_at: Any = 0
    content: str = ""
    group_id: str = ""
    user_id: str = ""

    @classmethod
    def from_row(cls, row: Any) -> "MemoryRecord":
        return cls(
            id=as_int(field_of(row, "id")),
            memory_type=str(field_of(row, "memory_type") or ""),
            importance=field_of(row, "importance", 0),
            created_at=field_of(row, "created_at", 0),
            content=str(field_of(row, "content") or ""),
            group_id=str(field_of(row, "group_id") or ""),
            user_id=str(field_of(row, "user_id") or ""),
        )


@dataclass(frozen=True)
class OrphanRecord:
    """A memory written after the last finish: the cursor never covered it."""

    memory_id: int
    memory_type: str
    importance: Any
    created_at: int


@dataclass(frozen=True)
class DecayAction:
    """An importance decay (and possibly archive) planned for one memory."""

    memory_id: int
    memory_type: str
    old_importance: int
    new_importance: int
    new_type: str
    reason: str = ""


@dataclass(frozen=True)
class Promotion:
    """An episodic -> auto_patrol consolidation planned for one memory."""

    memory_id: int
    theme: str
    old_type: str
    new_type: str
    old_importance: int
    new_importance: int
    rank: Any = None


@dataclass(frozen=True)
class IntentUpdate:
    """The deterministic downgrade applied to an expired intent."""

    memory_id: int
    memory_type: str
    importance: int
    content: str
    due: Any = None


@dataclass(frozen=True)
class IntentReport:
    """Classification of ``memory_type='intent'`` rows by their embedded due date."""

    pending: tuple[tuple[Any, Any], ...] = ()
    expired: tuple[tuple[Any, Any], ...] = ()
    badfmt: tuple[Any, ...] = ()


@dataclass(frozen=True)
class FileState:
    """A monitored file's current content fingerprint."""

    path: str
    md5: str
    mtime: float


@dataclass(frozen=True)
class FileChange:
    """A file reported by the audit snapshot diff."""

    path: str
    mtime: float
    md5: str = ""


@dataclass(frozen=True)
class AuditResult:
    """Result of ``classify_audit``: alerts, benign mtime-only refreshes, new snapshot."""

    suspicious: tuple[FileChange, ...] = ()
    benign: tuple[FileChange, ...] = ()
    snapshot: dict[str, str] = field(default_factory=dict)
    # Production aborts with AUDIT_ERROR when the ledger file is missing;
    # in that case no comparison happens and the snapshot must stay untouched.
    ledger_missing: bool = False
