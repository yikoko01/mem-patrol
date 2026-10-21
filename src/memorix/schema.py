"""Configurable SQL schema mapping / auto-detection (post-M4 generic adapter).

The native AstrBot schema has three tables (``memories`` / ``raw_messages`` /
``bot_messages``). Other projects have their own tables and column names; this
module maps them without touching the data:

* explicit mapping: a JSON file / inline JSON / ``Schema`` object;
* ``auto``: inspect the SQLite catalog and pick a memories table (+ optional
  message tables) by name/column aliases;
* memory-only mapping: message tables are optional — features that need them
  (status/finish) fail with a clear ``SchemaError`` instead of crashing.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SchemaError(RuntimeError):
    """The database cannot be mapped to the required logical tables/columns."""


def _check_ident(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or not _IDENT_RE.match(value):
        raise SchemaError("invalid %s identifier: %r" % (label, value))
    return value


@dataclass(frozen=True)
class ColumnSpec:
    """One logical table's physical mapping.

    Memory fields: id/type/importance/created_at/content/group_id/user_id.
    Message fields: id/timestamp/message/sender_id/sender_name/group_id.
    Unmapped fields are ``None`` and read as ``NULL`` / empty string.
    """

    table: str
    id: str = "id"
    type: str | None = "memory_type"
    importance: str | None = "importance"
    created_at: str | None = "created_at"
    content: str | None = "content"
    group_id: str | None = "group_id"
    user_id: str | None = "user_id"
    timestamp: str | None = "timestamp"
    message: str | None = "message"
    sender_id: str | None = "sender_id"
    sender_name: str | None = "sender_name"
    unit: str = "auto"  # auto / ms / s (informational; parse_ts already normalises)

    def __post_init__(self) -> None:
        object.__setattr__(self, "table", _check_ident(self.table, "table"))
        for field_name in (
            "id", "type", "importance", "created_at", "content", "group_id",
            "user_id", "timestamp", "message", "sender_id", "sender_name",
        ):
            object.__setattr__(self, field_name, _check_ident(getattr(self, field_name), field_name))
        unit = str(self.unit or "auto").lower()
        if unit not in {"auto", "ms", "s"}:
            raise SchemaError("invalid time unit %r (use auto/ms/s)" % self.unit)
        object.__setattr__(self, "unit", unit)

    def quoted(self, field_name: str) -> str | None:
        value = getattr(self, field_name)
        return '"%s"' % value if value else None


@dataclass(frozen=True)
class Schema:
    memories: ColumnSpec
    raw_messages: ColumnSpec | None = None
    bot_messages: ColumnSpec | None = None
    name: str = "custom"
    exclude_types: tuple[str, ...] = ("archived",)
    private_chat_by_group_equals_sender: bool = True

    def require_messages(self) -> None:
        if self.raw_messages is None or self.bot_messages is None:
            raise SchemaError(
                "this schema has no raw_messages/bot_messages mapping; "
                "status/finish need both (memory-only features still work)"
            )

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "memories": asdict(self.memories),
            "exclude": list(self.exclude_types),
            "private_chat_by_group_equals_sender": self.private_chat_by_group_equals_sender,
        }
        if self.raw_messages:
            data["raw_messages"] = asdict(self.raw_messages)
        if self.bot_messages:
            data["bot_messages"] = asdict(self.bot_messages)
        return data


def native_schema() -> Schema:
    return Schema(
        name="native",
        memories=ColumnSpec("memories"),
        raw_messages=ColumnSpec("raw_messages"),
        bot_messages=ColumnSpec("bot_messages"),
    )


def memory_only_schema(table: str = "memories") -> Schema:
    return Schema(
        name="memory-only",
        memories=ColumnSpec(table),
        raw_messages=None,
        bot_messages=None,
    )


def _spec_from_mapping(value: Mapping[str, Any], *, table: str | None = None) -> ColumnSpec:
    data = dict(value)
    if table and "table" not in data:
        data["table"] = table
    if "table" not in data:
        raise SchemaError("table mapping is missing 'table'")
    allowed = set(ColumnSpec.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise SchemaError("unknown schema fields: %s" % ", ".join(sorted(unknown)))
    # Explicit mapping: omitted optional columns are NULL, not "use the native
    # name" (SQLite returns the literal identifier for double-quoted missing
    # columns, which silently corrupts memory_type/importance).
    for field_name in allowed - {"table", "id"}:
        data.setdefault(field_name, None)
    return ColumnSpec(**data)


def schema_from_mapping(data: Mapping[str, Any]) -> Schema:
    if "memories" not in data:
        raise SchemaError("schema must define 'memories'")
    memories = _spec_from_mapping(data["memories"], table="memories")
    raw = _spec_from_mapping(data["raw_messages"]) if data.get("raw_messages") else None
    bot = _spec_from_mapping(data["bot_messages"]) if data.get("bot_messages") else None
    exclude = data.get("exclude", data.get("exclude_types", ("archived",)))
    if isinstance(exclude, str):
        exclude = (exclude,)
    return Schema(
        memories=memories,
        raw_messages=raw,
        bot_messages=bot,
        name=str(data.get("name") or "custom"),
        exclude_types=tuple(str(item) for item in (exclude or ())),
        private_chat_by_group_equals_sender=bool(
            data.get("private_chat_by_group_equals_sender", True)
        ),
    )


def schema_from_handoff(data: Mapping[str, Any]) -> Schema:
    """Parse the handoff schema form: ``{"tables": {"memories": {"columns": {...}}}}``.

    Handoff column keys are logical/physical names; per-column metadata may carry
    ``unit`` (ms/s) and ``exclude`` (e.g. archived). This is the form exported by
    the production audit (`memories-schema-note.md` §6).
    """
    tables = data.get("tables")
    if not isinstance(tables, Mapping) or "memories" not in tables:
        raise SchemaError("handoff schema needs tables.memories")
    exclude: list[str] = []
    private = True

    def convert(table_name: str, columns: Mapping[str, Any], logical_map: Mapping[str, str]) -> ColumnSpec:
        nonlocal private
        kwargs: dict[str, Any] = {"table": table_name}
        for logical, source_key in logical_map.items():
            if source_key not in columns:
                kwargs[logical] = None
                continue
            meta = columns[source_key]
            if isinstance(meta, Mapping):
                unit = meta.get("unit")
                if unit and logical in {"created_at", "timestamp"}:
                    kwargs["unit"] = str(unit)
                if logical == "type" and meta.get("exclude"):
                    exclude.extend(str(item) for item in meta["exclude"])
                note = str(meta.get("note") or "")
                if "private" in note.lower():
                    private = True
            kwargs[logical] = source_key
        if not kwargs.get("id") or not (kwargs.get("content") or kwargs.get("message")):
            raise SchemaError("handoff table %r needs id + content/message" % table_name)
        return ColumnSpec(**kwargs)

    memory_columns = (tables["memories"].get("columns") or {}) if isinstance(tables["memories"], Mapping) else {}
    memories = convert(
        "memories",
        memory_columns,
        {
            "id": "id", "content": "content", "type": "memory_type",
            "importance": "importance", "created_at": "created_at",
            "group_id": "group_id", "user_id": "user_id",
        },
    )
    raw = None
    bot = None
    if isinstance(tables.get("raw_messages"), Mapping):
        raw = convert(
            "raw_messages",
            tables["raw_messages"].get("columns") or {},
            {
                "id": "id", "timestamp": "timestamp", "message": "message",
                "sender_id": "sender_id", "sender_name": "sender_name",
                "group_id": "group_id",
            },
        )
    if isinstance(tables.get("bot_messages"), Mapping):
        bot = convert(
            "bot_messages",
            tables["bot_messages"].get("columns") or {},
            {"id": "id", "timestamp": "timestamp", "message": "message"},
        )
    return Schema(
        memories=memories,
        raw_messages=raw,
        bot_messages=bot,
        name=str(data.get("name") or "handoff"),
        exclude_types=tuple(exclude or ["archived"]),
        private_chat_by_group_equals_sender=private,
    )


def load_schema(value: str | Mapping[str, Any] | Schema | None) -> Schema:
    """Resolve a schema value: native/auto/memory-only/JSON file/inline JSON/mapping."""
    if isinstance(value, Schema):
        return value
    if value is None:
        return native_schema()
    if isinstance(value, Mapping):
        return schema_from_handoff(value) if "tables" in value else schema_from_mapping(value)
    text = str(value).strip()
    if text.lower() in {"native", "astrbot"}:
        return native_schema()
    if text.lower() in {"memory-only", "memory_only"}:
        return memory_only_schema()
    if text.lower() == "auto":
        raise SchemaError("'auto' needs a database connection; open SQLiteStore(path, schema='auto')")
    path = Path(text)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchemaError("unreadable schema file %s: %s" % (path, exc)) from exc
        return schema_from_handoff(data) if "tables" in data else schema_from_mapping(data)
    try:
        parsed = json.loads(text)
        return schema_from_handoff(parsed) if isinstance(parsed, dict) and "tables" in parsed else schema_from_mapping(parsed)
    except json.JSONDecodeError as exc:
        raise SchemaError("schema must be native/auto/memory-only/JSON: %s" % exc) from exc


# ── auto-detection ───────────────────────────────────────────────────
_MEMORY_TABLE_CANDIDATES = ("memories", "memory", "long_term_memory", "memory_records", "knowledge", "notes")
_RAW_TABLE_CANDIDATES = ("raw_messages", "messages", "chat_messages", "message_log")
_BOT_TABLE_CANDIDATES = ("bot_messages", "assistant_messages", "bot_replies")
_MEMORY_COLUMNS = {
    "id": ("id", "memory_id", "pk"),
    "content": ("content", "text", "body", "memory", "summary", "value"),
    "type": ("memory_type", "type", "kind", "category", "label"),
    "importance": ("importance", "weight", "score", "priority", "rank"),
    "created_at": ("created_at", "created", "created_time", "timestamp", "time", "ts"),
    "group_id": ("group_id", "group", "chat_id", "session_id"),
    "user_id": ("user_id", "user", "uid", "owner_id"),
}
_MESSAGE_COLUMNS = {
    "id": ("id", "message_id", "pk"),
    "timestamp": ("timestamp", "ts", "time", "created_at", "created"),
    "message": ("message", "text", "body", "content"),
    "sender_id": ("sender_id", "user_id", "uid", "from_id"),
    "sender_name": ("sender_name", "name", "nickname", "display_name"),
    "group_id": ("group_id", "group", "chat_id", "session_id"),
}


def _pick(columns: set[str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute('pragma table_info("%s")' % table).fetchall()}


def _find_table(conn: sqlite3.Connection, candidates: tuple[str, ...]) -> str | None:
    tables = {str(row[0]) for row in conn.execute("select name from sqlite_master where type='table'")}
    for candidate in candidates:
        if candidate in tables:
            return candidate
    for table in sorted(tables):
        if any(candidate in table for candidate in candidates):
            return table
    return None


def _spec_for(conn: sqlite3.Connection, table: str, mapping: Mapping[str, tuple[str, ...]]) -> ColumnSpec:
    columns = _table_columns(conn, table)
    kwargs: dict[str, str | None] = {"table": table}
    for field_name, aliases in mapping.items():
        kwargs[field_name] = _pick(columns, aliases)
    if not kwargs.get("id") or not (kwargs.get("content") or kwargs.get("message")):
        raise SchemaError("table %r needs id + content/message-like columns (found %s)" % (table, sorted(columns)))
    return ColumnSpec(**kwargs)


def autodetect_schema(conn: sqlite3.Connection) -> Schema:
    memory_table = _find_table(conn, _MEMORY_TABLE_CANDIDATES)
    if memory_table is None:
        raise SchemaError(
            "no memories-like table found; pass an explicit --schema JSON "
            "(tables: %s)" % sorted(str(row[0]) for row in conn.execute("select name from sqlite_master where type='table'"))
        )
    memories = _spec_for(conn, memory_table, _MEMORY_COLUMNS)
    raw_table = _find_table(conn, _RAW_TABLE_CANDIDATES)
    bot_table = _find_table(conn, _BOT_TABLE_CANDIDATES)
    raw = None
    bot = None
    if raw_table:
        try:
            raw = _spec_for(conn, raw_table, _MESSAGE_COLUMNS)
        except SchemaError:
            raw = None
    if bot_table:
        try:
            bot = _spec_for(conn, bot_table, _MESSAGE_COLUMNS)
        except SchemaError:
            bot = None
    return Schema(memories=memories, raw_messages=raw, bot_messages=bot, name="auto")
