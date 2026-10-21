"""Storage adapter over a SQLite database with a configurable schema.

Native three-table schema (originated in AstrBot, not a dependency) is the
default; foreign schemas are supported through
``schema.Schema`` (explicit JSON mapping or ``auto`` detection). Only the
memories table is required; message tables are optional and message-dependent
features raise a clear ``SchemaError`` when they are absent.
"""
from __future__ import annotations

import itertools
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

from .models import (
    DecayAction,
    IntentUpdate,
    MemoryRecord,
    Promotion,
    field_of,
)
from .schema import (
    ColumnSpec,
    Schema,
    SchemaError,
    autodetect_schema,
    load_schema,
)

REQUIRED_TABLES = frozenset({"memories"})
_MESSAGE_TABLES = frozenset({"raw_messages", "bot_messages"})
_BACKUP_SEQ = itertools.count(1)


def readonly_uri(path: str | Path) -> str:
    """Build a SQLite read-only URI that survives '?', '#', '%' and spaces in paths."""
    encoded = str(path)
    for char, replacement in (("%", "%25"), ("?", "%3F"), ("#", "%23"), (" ", "%20")):
        encoded = encoded.replace(char, replacement)
    return "file:%s?mode=ro" % encoded


class StoreError(RuntimeError):
    """Database missing/corrupt/incompatible."""


class ReadOnlyStoreError(StoreError):
    """A write was attempted through a read-only adapter."""


class _SchemaError(SchemaError):
    """Alias kept for backwards compatibility with earlier imports."""


def _backup_stamp() -> str:
    return "%s-p%d-%06d-%04d" % (
        time.strftime("%Y%m%d-%H%M%S", time.localtime()),
        os.getpid(),
        (time.time_ns() // 1000) % 1_000_000,
        next(_BACKUP_SEQ),
    )


def _table_sql(table: str) -> str:
    if table not in _MESSAGE_TABLES:
        raise StoreError("unknown message table: %r" % (table,))
    return table  # validated against a fixed allow-list


class SQLiteStore:
    """Thin SQLite adapter. Use as a context manager or call :meth:`close`."""

    def __init__(
        self,
        path: str | Path,
        *,
        readonly: bool = True,
        schema: Schema | str | Path | dict | None = None,
    ) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise StoreError("database not found: %s" % self.path)
        self.readonly = bool(readonly)
        uri = readonly_uri(self.path) if self.readonly else str(self.path)
        self.conn = sqlite3.connect(uri, uri=self.readonly)
        self.conn.row_factory = sqlite3.Row
        if self.readonly:
            self.conn.execute("PRAGMA query_only=ON")
        if isinstance(schema, str) and schema.strip().lower() == "auto":
            self.schema = autodetect_schema(self.conn)
        else:
            self.schema = load_schema(schema)

    # ── lifecycle ──────────────────────────────────────────────────────
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ── schema / reads ────────────────────────────────────────────────
    def table_names(self) -> set[str]:
        rows = self.conn.execute(
            "select name from sqlite_master where type='table'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    def require_schema(self) -> None:
        if self.schema.memories.table not in self.table_names():
            raise SchemaError(
                "missing memories table %r; pass --schema for a foreign database"
                % self.schema.memories.table
            )

    def require_messages(self) -> None:
        self.schema.require_messages()
        tables = self.table_names()
        for name, spec in (("raw_messages", self.schema.raw_messages), ("bot_messages", self.schema.bot_messages)):
            if spec is None or spec.table not in tables:
                raise SchemaError(
                    "missing %s table %r; status/finish need configured message tables"
                    % (name, spec.table if spec else None)
                )

    def _memory_select(self, *, columns: str | None = None) -> str:
        spec = self.schema.memories

        def part(field_name: str, alias: str, default: str = "NULL") -> str:
            quoted = spec.quoted(field_name)
            return '%s AS "%s"' % (quoted, alias) if quoted else '%s AS "%s"' % (default, alias)

        selected = columns or ", ".join(
            [
                part("id", "id", "0"),
                part("type", "memory_type", "''"),
                part("importance", "importance", "0"),
                part("created_at", "created_at", "0"),
                part("content", "content", "''"),
                part("group_id", "group_id", "''"),
                part("user_id", "user_id", "''"),
            ]
        )
        return 'select %s from "%s"' % (selected, spec.table)

    def iter_memories(self, types: Sequence[str] | None = None) -> list[MemoryRecord]:
        spec = self.schema.memories
        sql = self._memory_select()
        params: list[str] = []
        if types:
            if spec.type is None:
                raise SchemaError("schema has no memory_type column; cannot filter by type")
            sql += ' where "%s" in (%s)' % (spec.type, ",".join("?" for _ in types))
            params = list(types)
        sql += ' order by "%s"' % (spec.id or "id")
        return [MemoryRecord.from_row(row) for row in self.conn.execute(sql, params)]

    def get_memory(self, memory_id: int) -> MemoryRecord | None:
        spec = self.schema.memories
        row = self.conn.execute(
            '%s where "%s" = ?' % (self._memory_select(), spec.id or "id"),
            (memory_id,),
        ).fetchone()
        return MemoryRecord.from_row(row) if row is not None else None

    def memories_by_id(self, memory_ids: Iterable[int]) -> dict[int, MemoryRecord]:
        spec = self.schema.memories
        wanted = [int(memory_id) for memory_id in memory_ids]
        if not wanted:
            return {}
        placeholders = ",".join("?" for _ in wanted)
        rows = self.conn.execute(
            '%s where "%s" in (%s)' % (self._memory_select(), spec.id or "id", placeholders),
            wanted,
        ).fetchall()
        return {int(field_of(row, "id")): MemoryRecord.from_row(row) for row in rows}

    def count_by_type(self) -> dict[str, int]:
        spec = self.schema.memories
        if spec.type is None:
            total = self.conn.execute('select count(*) from "%s"' % spec.table).fetchone()[0]
            return {"memory": int(total)}
        rows = self.conn.execute(
            'select "%s", count(*) from "%s" group by "%s" order by 2 desc'
            % (spec.type, spec.table, spec.type)
        ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def _message_spec(self, table: str) -> ColumnSpec:
        spec = self.schema.raw_messages if table == "raw_messages" else self.schema.bot_messages
        if spec is None:
            raise SchemaError("schema has no %s mapping" % table)
        if spec.table not in self.table_names():
            raise SchemaError("missing %s table %r" % (table, spec.table))
        return spec

    @staticmethod
    def _message_select(spec: ColumnSpec) -> str:
        def part(field_name: str, alias: str, default: str = "''") -> str:
            quoted = spec.quoted(field_name)
            return '%s AS "%s"' % (quoted, alias) if quoted else '%s AS "%s"' % (default, alias)

        selected = ", ".join(
            [
                part("id", "id", "0"),
                part("timestamp", "timestamp", "0"),
                part("message", "message", "''"),
                part("sender_id", "sender_id", "''"),
                part("sender_name", "sender_name", "''"),
                part("group_id", "group_id", "''"),
            ]
        )
        return 'select %s from "%s"' % (selected, spec.table)

    def max_message_ids(self) -> tuple[int, int]:
        self.require_messages()
        raw, bot = self.schema.raw_messages, self.schema.bot_messages
        assert raw is not None and bot is not None
        user = self.conn.execute('select coalesce(max("%s"), 0) from "%s"' % (raw.id, raw.table)).fetchone()[0]
        bot_max = self.conn.execute('select coalesce(max("%s"), 0) from "%s"' % (bot.id, bot.table)).fetchone()[0]
        return int(user), int(bot_max)

    def fetch_messages(self, table: str, after_id: int, limit: int) -> list[sqlite3.Row]:
        """Rows with ``id > after_id`` in ascending order (never "last N").

        A non-positive limit returns no rows instead of SQLite's ``LIMIT -1``
        (which would silently mean "unlimited").
        """
        safe_table = _table_sql(table)
        spec = self._message_spec(safe_table)
        bounded = max(0, int(limit))
        if bounded == 0:
            return []
        return self.conn.execute(
            '%s where "%s" > ? order by "%s" asc limit ?'
            % (self._message_select(spec), spec.id, spec.id),
            (int(after_id), bounded),
        ).fetchall()

    def recent_private_messages(self, user_id: str, limit: int = 4) -> list[sqlite3.Row]:
        """Newest-first private inbound messages for one user.

        Production rule from the schema handoff: in ``raw_messages`` a private
        chat has ``group_id == sender_id``; group chats have a real group id.
        """
        spec = self._message_spec("raw_messages")
        if not spec.sender_id:
            return []
        bounded = max(0, int(limit))
        if bounded == 0:
            return []
        conditions = ['"%s" = ?' % spec.sender_id]
        params: list[object] = [str(user_id)]
        if spec.group_id and self.schema.private_chat_by_group_equals_sender:
            conditions.append(
                '("%s" = "%s" or "%s" is null or "%s" = \'\')'
                % (spec.group_id, spec.sender_id, spec.group_id, spec.group_id)
            )
        sql = '%s where %s order by "%s" desc limit ?' % (
            self._message_select(spec),
            " and ".join(conditions),
            spec.id,
        )
        return self.conn.execute(sql, [*params, bounded]).fetchall()

    def sender_name_rows(self) -> list[sqlite3.Row]:
        spec = self._message_spec("raw_messages")
        if not spec.sender_id or not spec.sender_name:
            return []
        return self.conn.execute(
            'select "%s" AS sender_id, "%s" AS sender_name from "%s" '
            'where "%s" is not null and trim("%s") <> \'\' group by "%s"'
            % (
                spec.sender_id, spec.sender_name, spec.table,
                spec.sender_name, spec.sender_name, spec.sender_id,
            )
        ).fetchall()

    # ── writes (require readonly=False) ──────────────────────────────
    def _ensure_writable(self) -> None:
        if self.readonly:
            raise ReadOnlyStoreError(
                "adapter is read-only; re-open with readonly=False and take a backup first"
            )

    def _require_memory_write_fields(self, *, content: bool = False) -> None:
        spec = self.schema.memories
        required = ["type", "importance"] + (["content"] if content else [])
        missing = [name for name in required if getattr(spec, name) is None]
        if missing:
            raise SchemaError(
                "schema lacks writable memories column(s): %s; refusing to write"
                % ", ".join(missing)
            )

    def _apply(self, sql: str, rows: Iterable[tuple]) -> int:
        self._ensure_writable()
        changed = 0
        with self.conn:  # single transaction; rollback on exception
            for params in rows:
                cursor = self.conn.execute(sql, params)
                if cursor.rowcount != 1:
                    raise StoreError(
                        "update affected %d rows (expected 1) for %r"
                        % (cursor.rowcount, params)
                    )
                changed += 1
        return changed

    def apply_intent_updates(self, updates: Iterable[IntentUpdate]) -> int:
        self._require_memory_write_fields(content=True)
        spec = self.schema.memories
        return self._apply(
            'update "%s" set "%s" = ?, "%s" = ?, "%s" = ? where "%s" = ?'
            % (spec.table, spec.type, spec.importance, spec.content, spec.id),
            ((u.memory_type, u.importance, u.content, u.memory_id) for u in updates),
        )

    def apply_decay_actions(self, actions: Iterable[DecayAction]) -> int:
        self._require_memory_write_fields()
        spec = self.schema.memories
        return self._apply(
            'update "%s" set "%s" = ?, "%s" = ? where "%s" = ?'
            % (spec.table, spec.type, spec.importance, spec.id),
            ((a.new_type, a.new_importance, a.memory_id) for a in actions),
        )

    def apply_promotions(self, promotions: Iterable[Promotion]) -> int:
        self._require_memory_write_fields()
        spec = self.schema.memories
        return self._apply(
            'update "%s" set "%s" = ?, "%s" = ? where "%s" = ?'
            % (spec.table, spec.type, spec.importance, spec.id),
            ((p.new_type, p.new_importance, p.memory_id) for p in promotions),
        )

    def backup_to(self, destination: str | Path) -> Path:
        """Consistent online backup (works from a read-only handle too)."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(destination)) as target:
            self.conn.backup(target)
        return destination


def backup_database(db_path: str | Path, backup_dir: str | Path, tag: str = "preapply") -> Path:
    """Snapshot ``db_path`` into ``backup_dir`` before any write."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise StoreError("database not found: %s" % db_path)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _backup_stamp()
    destination = backup_dir / ("%s-%s-%s.db" % (db_path.stem, tag, stamp))
    source = sqlite3.connect(readonly_uri(db_path), uri=True)
    try:
        with sqlite3.connect(str(destination)) as target:
            source.backup(target)
    finally:
        source.close()
    return destination


def copy_file_backup(path: str | Path, backup_dir: str | Path, tag: str = "preapply") -> Path | None:
    """Copy a non-DB state file aside before overwriting it."""
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _backup_stamp()
    destination = backup_dir / ("%s-%s-%s" % (path.name, tag, stamp))
    shutil.copy2(path, destination)
    return destination
