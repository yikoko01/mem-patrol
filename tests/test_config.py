"""M1 path configuration: explicit flags win, env is a fallback, db is mandatory."""
from __future__ import annotations

import pytest

from memorix.config import (
    ConfigError,
    ENV_AUDIT_GLOBS,
    ENV_DB,
    resolve_paths,
)


def test_explicit_db_only():
    paths = resolve_paths(db="/tmp/x.db", env={})
    assert str(paths.db) == "/tmp/x.db"
    assert paths.state is None
    assert paths.audit_globs == ()


def test_env_database_fallback():
    paths = resolve_paths(env={ENV_DB: "/tmp/from-env.db"})
    assert str(paths.db) == "/tmp/from-env.db"


def test_explicit_flag_overrides_env():
    paths = resolve_paths(db="/tmp/cli.db", env={ENV_DB: "/tmp/env.db"})
    assert str(paths.db) == "/tmp/cli.db"


def test_missing_db_is_an_error():
    with pytest.raises(ConfigError):
        resolve_paths(env={})


def test_audit_globs_from_env_are_pathsep_split():
    paths = resolve_paths(
        db="/tmp/x.db",
        env={ENV_AUDIT_GLOBS: "/tmp/a/*.json" + ":" + "/tmp/b/*.json"},
    )
    assert paths.audit_globs == ("/tmp/a/*.json", "/tmp/b/*.json")


def test_explicit_globs_win_over_env():
    paths = resolve_paths(
        db="/tmp/x.db",
        audit_globs=("/tmp/cli/*.json",),
        env={ENV_AUDIT_GLOBS: "/tmp/env/*.json"},
    )
    assert paths.audit_globs == ("/tmp/cli/*.json",)


def test_backups_default_to_db_sibling():
    paths = resolve_paths(db="/tmp/data/messages.db", env={})
    assert paths.backups.as_posix().endswith("/tmp/data/memorix-backups")


def test_backup_dir_override(tmp_path):
    paths = resolve_paths(db="/tmp/x.db", backup_dir=str(tmp_path / "bk"), env={})
    assert paths.backups == tmp_path / "bk"


def test_audit_only_backups_default_next_to_snapshot(tmp_path):
    paths = resolve_paths(
        ledger=str(tmp_path / "ledger.md"),
        audit_snapshot=str(tmp_path / "snap.json"),
        require_db=False,
    )
    assert paths.backups == tmp_path / "memorix-backups"
