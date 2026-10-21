"""MCP tool definitions + read-only implementations.

Every tool is read-only: no ``--apply`` path is exposed over MCP. Writes stay in
the CLI where a human runs them with an explicit apply flag and backup.

The server resolves the default DB from ``--db`` or ``MEMORIX_DB``.
"""
from __future__ import annotations

from typing import Any, Mapping

from ..adapters.files import fingerprint_patterns, load_snapshot
from ..config import Paths, resolve_paths
from ..diagnose import build_diagnosis, format_diagnosis
from ..eval.runner import EvalReport, run_all, run_suite
from ..gatekeep import Context, decide
from ..gatekeep.bench import load_cases as load_judge_cases
from ..gatekeep.bench import run_cases as run_judge_cases
from ..ledger import mtime, read_text
from ..policy.audit import classify_audit
from ..retrieval.context import recent_private_context
from ..retrieval.score import recall
from ..retrieval.store import load_rows
from ..state import load_state
from ..schema import SchemaError
from ..store import SQLiteStore


class ToolError(RuntimeError):
    """Raised when a tool call is invalid or its input cannot be used."""


def _diagnose(arguments: Mapping[str, Any], default_db: str | None) -> str:
    db = arguments.get("db") or default_db
    if not db:
        raise ToolError("db is required (tool argument or server --db / MEMORIX_DB)")
    paths = resolve_paths(
        db=str(db),
        state=arguments.get("state"),
        ledger=arguments.get("ledger"),
        audit_snapshot=arguments.get("audit_snapshot"),
        audit_globs=tuple(arguments.get("config") or ()),
        schema=arguments.get("schema"),
    )
    with SQLiteStore(paths.db, readonly=True, schema=paths.schema) as store:
        store.require_schema()
        memories = store.iter_memories()
        try:
            user_max, bot_max = store.max_message_ids()
        except SchemaError:  # memory-only schema has no message tables
            user_max = bot_max = None
    audit = None
    if paths.ledger and paths.audit_globs:
        ledger_text = read_text(paths.ledger)
        if ledger_text is None:
            from ..models import AuditResult

            audit = AuditResult(ledger_missing=True)
        else:
            previous = load_snapshot(paths.audit_snapshot) if paths.audit_snapshot else {}
            audit = classify_audit(
                previous,
                fingerprint_patterns(paths.audit_globs),
                ledger_text,
                mtime(paths.ledger),
            )
    diagnosis = build_diagnosis(
        memories,
        state=load_state(paths.state),
        audit=audit,
        now=int(arguments.get("now") or 0) or None,
        user_max=user_max,
        bot_max=bot_max,
    )
    return format_diagnosis(diagnosis)


def _orphan(arguments: Mapping[str, Any], default_db: str | None) -> str:
    from ..policy.orphan import detect_orphans

    db = arguments.get("db") or default_db
    if not db:
        raise ToolError("db is required")
    paths = resolve_paths(db=str(db), state=arguments.get("state"), schema=arguments.get("schema"))
    state = load_state(paths.state)
    if state is None:
        return "ORPHAN_SKIP 尚无收尾记录"
    with SQLiteStore(paths.db, readonly=True, schema=paths.schema) as store:
        store.require_schema()
        memories = store.iter_memories()
    orphans = detect_orphans(memories, state.last_finish_ts)
    if not orphans:
        return "ORPHAN_NONE"
    return "ORPHAN %d: %s" % (
        len(orphans),
        ", ".join("#%s %s" % (item.memory_id, item.memory_type) for item in orphans),
    )


def _recall(arguments: Mapping[str, Any], default_db: str | None) -> str:
    db = arguments.get("db") or default_db
    if not db:
        raise ToolError("db is required")
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ToolError("query is required")
    context = str(arguments.get("context") or "")
    if not context and arguments.get("user_id"):
        context = recent_private_context(
            str(db),
            str(arguments["user_id"]),
            limit=4,
            schema=arguments.get("schema"),
        )
    rows = load_rows(
        str(db),
        as_of_ms=arguments.get("as_of_ms"),
        schema=arguments.get("schema"),
    )
    text = recall(
        query,
        rows=rows,
        context=context,
        group_id=str(arguments.get("group_id") or ""),
        user_id=str(arguments.get("user_id") or ""),
        top_k=max(1, min(10, int(arguments.get("top_k") or 5))),
        max_chars=max(240, min(1800, int(arguments.get("max_chars") or 900))),
    )
    return text or "(empty)"


def _gate_check(arguments: Mapping[str, Any], default_db: str | None) -> str:
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise ToolError("text is required")
    config = arguments.get("config") if isinstance(arguments.get("config"), dict) else {}
    ctx = Context(
        text=text,
        group_id=str(arguments.get("group_id") or ""),
        directed=bool(arguments.get("directed", False)),
        scene_trigger=str(arguments.get("scene_trigger") or ""),
        config=dict(config),
    )
    outcome = decide(ctx)  # no judge: pure deterministic gates
    lines = ["ACTION=%s REASON=%s" % (outcome.action, outcome.reason)]
    for item in outcome.trace:
        lines.append(
            "  %s allowed=%s weight=%s%s"
            % (
                item.gate,
                item.result.allowed,
                item.result.weight,
                (" reason=%s" % item.result.reason) if item.result.reason else "",
            )
        )
    return "\n".join(lines)


def _judge_replay(arguments: Mapping[str, Any], default_db: str | None) -> str:
    results = run_judge_cases(load_judge_cases())
    failed = [result for result in results if not result.ok]
    lines = ["JUDGE_REPLAY %d/%d" % (len(results) - len(failed), len(results))]
    for result in failed:
        lines.append("FAIL %s: %s" % (result.case_id, result.detail))
    return "\n".join(lines)


def _eval(arguments: Mapping[str, Any], default_db: str | None) -> str:
    suite = str(arguments.get("suite") or "all")
    report = run_all() if suite == "all" else EvalReport((run_suite(suite),))
    lines = ["EVAL %d/%d" % (report.passed, report.passed + report.failed)]
    for item in report.suites:
        lines.append("%s passed=%d failed=%d" % (item.name, item.passed, item.failed))
    return "\n".join(lines)


_DB = {"type": "string", "description": "patrol SQLite database path"}
_DISPATCH = {
    "memorix_diagnose": _diagnose,
    "memorix_orphan": _orphan,
    "memorix_recall": _recall,
    "memorix_gate_check": _gate_check,
    "memorix_judge_replay": _judge_replay,
    "memorix_eval": _eval,
}

TOOL_DEFS: list[dict] = [
    {
        "name": "memorix_diagnose",
        "description": "Read-only health diagnosis of a patrol database (orphans, decay, intents, audit drift, data quality).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": _DB,
                "schema": {"type": "string", "description": "native/auto/JSON schema mapping for foreign DBs"},
                "state": {"type": "string", "description": "last_patrol.json path"},
                "ledger": {"type": "string", "description": "change_history.md path"},
                "audit_snapshot": {"type": "string", "description": "audit fingerprint snapshot path"},
                "config": {"type": "array", "items": {"type": "string"}, "description": "config globs to audit"},
                "now": {"type": "integer", "description": "override the epoch clock for reproducible diagnosis"},
            },
            "required": ["db"],
        },
    },
    {
        "name": "memorix_orphan",
        "description": "List orphan batches (memories written after the last finish).",
        "inputSchema": {
            "type": "object",
            "properties": {"db": _DB, "schema": {"type": "string"}, "state": {"type": "string"}},
            "required": ["db"],
        },
    },
    {
        "name": "memorix_recall",
        "description": "Lexical memory recall (anchor-aware) against a patrol database; returns the prompt-ready block.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db": _DB,
                "schema": {"type": "string", "description": "native/auto/JSON schema mapping for foreign DBs"},
                "query": {"type": "string", "description": "the user's own words (never an instruction wrapper)"},
                "context": {"type": "string", "description": "recent messages, newest first"},
                "group_id": {"type": "string"},
                "user_id": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                "max_chars": {"type": "integer", "minimum": 240, "maximum": 1800},
                "as_of_ms": {"type": "integer", "description": "point-in-time replay cut (epoch ms)"},
            },
            "required": ["db", "query"],
        },
    },
    {
        "name": "memorix_gate_check",
        "description": "Run the deterministic gatekeep gates (no LLM) on a candidate message; returns action + per-gate trace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "group_id": {"type": "string"},
                "directed": {"type": "boolean"},
                "scene_trigger": {"type": "string"},
                "config": {"type": "object", "description": "gate config snapshot (enable_group_interjection, caps, ...)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "memorix_judge_replay",
        "description": "Run the judge replay corpus (9 cases) and report pass/fail.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memorix_eval",
        "description": "Run the offline evaluation suites (recall/judge/policy) or one of them.",
        "inputSchema": {
            "type": "object",
            "properties": {"suite": {"type": "string", "enum": ["all", "recall", "judge", "policy"]}},
        },
    },
]


def call_tool(name: str, arguments: Mapping[str, Any] | None, *, default_db: str | None = None) -> str:
    handler = _DISPATCH.get(name)
    if handler is None:
        raise ToolError("unknown tool: %s" % name)
    return handler(arguments or {}, default_db)
