"""Path resolution for M1.

No production path is hardcoded in the package. Every path comes from an
explicit CLI flag or a ``MEMORIX_*`` environment variable; a missing required
path is an error, never a silent fallback to /root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ENV_DB = "MEMORIX_DB"
ENV_STATE = "MEMORIX_STATE"
ENV_LEDGER = "MEMORIX_LEDGER"
ENV_AUDIT_SNAPSHOT = "MEMORIX_AUDIT_SNAPSHOT"
ENV_AUDIT_GLOBS = "MEMORIX_AUDIT_GLOBS"  # os.pathsep separated
ENV_BACKUP_DIR = "MEMORIX_BACKUP_DIR"
ENV_SCHEMA = "MEMORIX_SCHEMA"


class ConfigError(RuntimeError):
    """Required path/configuration is missing or contradictory."""


@dataclass(frozen=True)
class Paths:
    """All filesystem entry points of one memorix run."""

    db: Path | None
    state: Path | None = None
    ledger: Path | None = None
    audit_snapshot: Path | None = None
    audit_globs: tuple[str, ...] = ()
    backup_dir: Path | None = None
    schema: str | None = None

    @property
    def backups(self) -> Path:
        """Where M1 puts DB snapshots before applying a fix."""
        if self.backup_dir is not None:
            return self.backup_dir
        if self.db is not None:
            return self.db.parent / "memorix-backups"
        if self.audit_snapshot is not None:
            return self.audit_snapshot.parent / "memorix-backups"
        return Path("memorix-backups")


def _pick(cli_value: str | None, env: Mapping[str, str], key: str) -> str | None:
    if cli_value:
        return cli_value
    return env.get(key) or None


def _as_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def resolve_paths(
    *,
    db: str | None = None,
    state: str | None = None,
    ledger: str | None = None,
    audit_snapshot: str | None = None,
    audit_globs: tuple[str, ...] = (),
    backup_dir: str | None = None,
    schema: str | None = None,
    env: Mapping[str, str] | None = None,
    require_db: bool = True,
) -> Paths:
    """Resolve explicit flags first, then env vars.

    ``db`` is mandatory for DB commands; file-only commands (``audit``) pass
    ``require_db=False`` so they can run without a database.
    """
    env = os.environ if env is None else env

    db_value = _pick(db, env, ENV_DB)
    if not db_value and require_db:
        raise ConfigError("db path is required: use --db or MEMORIX_DB")

    globs = tuple(audit_globs or ())
    if not globs:
        raw = env.get(ENV_AUDIT_GLOBS) or ""
        globs = tuple(part for part in raw.split(os.pathsep) if part)

    return Paths(
        db=Path(db_value) if db_value else None,
        state=_as_path(_pick(state, env, ENV_STATE)),
        ledger=_as_path(_pick(ledger, env, ENV_LEDGER)),
        audit_snapshot=_as_path(_pick(audit_snapshot, env, ENV_AUDIT_SNAPSHOT)),
        audit_globs=globs,
        backup_dir=_as_path(_pick(backup_dir, env, ENV_BACKUP_DIR)),
        schema=_pick(schema, env, ENV_SCHEMA),
    )
