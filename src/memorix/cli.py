"""memorix CLI — the deterministic steps of the patrol state machine (M1).

Design (approved decision #3, hybrid):
* every path is explicit (``--db`` / ``--state`` / ``--ledger`` / ...), no
  production path is baked in;
* read-only by default; every mutation requires ``--apply`` and is preceded by
  a snapshot;
* semantic choices are NOT guessed: ``status`` prints the batch, ``consolidate
  --show`` prints the recent-episodic window for an LLM, and ``consolidate
  --apply-file`` validates the externally produced plan.

Exit codes: 0 ok, 1 ``--strict`` finding, 2 usage/validation, 3 finish refused,
4 config/store/state error.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .adapters.files import fingerprint_patterns, load_snapshot, save_snapshot
from .config import ConfigError, Paths, resolve_paths
from .schema import SchemaError
from .diagnose import build_diagnosis, format_diagnosis
from .ledger import last_mark, mtime, read_text
from .policy.audit import classify_audit
from .policy.consolidation import recent_episodic, validate_plan
from .policy.decay import plan_decay
from .policy.finish_gate import verify_finish
from .policy.intents import classify_intents, plan_intent_expiry
from .policy.orphan import ORPHAN_MEMORY_TYPES, detect_orphans
from .policy.senders import build_sender_name_map, display_sender
from .policy.timeparse import parse_ts
from .state import (
    MAX_BOT_MSGS,
    MAX_CHARS,
    MAX_USER_MSGS,
    PatrolState,
    StateError,
    advance_after_finish,
    decide_status,
    initial_state,
    load_state,
    save_state,
)
from .store import (
    SQLiteStore,
    StoreError,
    backup_database,
    copy_file_backup,
)


# ── shared plumbing ──────────────────────────────────────────────────
def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="path to the patrol SQLite database")
    parser.add_argument("--state", help="path to the patrol cursor state JSON")
    parser.add_argument("--ledger", help="path to the change-history ledger file")
    parser.add_argument("--audit-snapshot", help="path to the audit fingerprint snapshot")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="GLOB",
        help="config file glob to audit (repeatable)",
    )
    parser.add_argument("--backup-dir", help="where snapshots go before --apply (default: <db>/../memorix-backups)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--now", type=int, help="override the epoch clock (reproducible runs)")
    parser.add_argument("--schema", help="schema mapping: native/auto/JSON file/inline JSON (foreign DBs)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memorix",
        description="Deterministic memory-patrol kernel: diagnose and repair.",
    )
    parser.add_argument("--version", action="version", version="mem-patrol " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("diagnose", help="read-only health report (findings by severity)")
    _common(p)
    p.add_argument("--strict", action="store_true", help="exit 1 when a HIGH finding exists")
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("recall", help="prompt-ready lexical recall")
    _common(p)
    p.add_argument("--query", required=True, help="the user's own words")
    p.add_argument("--context", default="", help="recent conversation context (optional)")
    p.add_argument("--user-id", default="", help="filter/boost a user; builds private context if --context is empty")
    p.add_argument("--group-id", default="", help="group filter/boost")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--max-chars", type=int, default=900)
    p.add_argument("--as-of-ms", type=int, help="point-in-time cutoff (epoch milliseconds)")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("orphan", help="list orphan batches (written but cursor not advanced)")
    _common(p)
    p.set_defaults(func=cmd_orphan)

    p = sub.add_parser("status", help="first-run / SKIP / WORK decision + batch digest")
    _common(p)
    p.add_argument("--apply", action="store_true", help="initialise the cursor or persist pending boundaries")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("audit", help="config drift vs ledger (fingerprint first, ledger mention second)")
    _common(p)
    p.add_argument("--apply", action="store_true", help="write the new fingerprint snapshot")
    p.add_argument("--strict", action="store_true", help="exit 1 when a suspicious change exists")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("intents", help="intent TTL report / downgrade expired intents")
    _common(p)
    p.add_argument("--apply", action="store_true", help="apply the deterministic downgrade (with DB snapshot)")
    p.set_defaults(func=cmd_intents)

    p = sub.add_parser("decay", help="decay plan (SOP: >30d and importance<=3)")
    _common(p)
    p.add_argument("--apply", action="store_true", help="apply the decay plan (with DB snapshot)")
    p.set_defaults(func=cmd_decay)

    p = sub.add_parser("finish", help="finish gate + cursor advance")
    _common(p)
    p.add_argument("--user-end", type=int, help="BATCH_END_USER from status")
    p.add_argument("--bot-end", type=int, help="BATCH_END_BOT from status")
    p.add_argument("--mem-ids", required=True, help="comma-separated memory ids, or 'none'")
    p.add_argument("--ledger-mark", required=True, help="this round's ledger heading, or 'none'")
    p.add_argument("--apply", action="store_true", help="advance the cursor (with state snapshot)")
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("profile", help="show use-case presets (chat / project / both)")
    p.add_argument("--name", default="both", choices=["chat", "project", "both"])
    p.add_argument("--list", action="store_true")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("consolidate", help="episodic->auto_patrol: show window / validate a plan")
    _common(p)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true", help="print the recent-episodic window as JSON for an LLM")
    group.add_argument("--apply-file", help="apply a validated JSON plan [{memory_id, theme, ...}]")
    p.add_argument("--apply", action="store_true", help="write the promotions (with DB snapshot)")
    p.set_defaults(func=cmd_consolidate)

    return parser


def _paths(args: argparse.Namespace, *, require_db: bool = True) -> Paths:
    return resolve_paths(
        db=args.db,
        state=args.state,
        ledger=args.ledger,
        audit_snapshot=args.audit_snapshot,
        audit_globs=tuple(args.config or ()),
        backup_dir=args.backup_dir,
        schema=args.schema,
        require_db=require_db,
    )


def _now(args: argparse.Namespace) -> int:
    return int(args.now) if args.now is not None else int(time.time())


def _load_state(paths: Paths) -> PatrolState | None:
    return load_state(paths.state)


def _open_read(paths: Paths) -> SQLiteStore:
    store = SQLiteStore(paths.db, readonly=True, schema=paths.schema)
    store.require_schema()
    return store


def _emit_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _fmt_ts(timestamp: int | float | None) -> str:
    if not timestamp:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(timestamp)))


def _run_audit(paths: Paths):
    if not paths.ledger or not paths.audit_globs:
        return None
    ledger_text = read_text(paths.ledger)
    if ledger_text is None:
        from .models import AuditResult

        return AuditResult(ledger_missing=True)
    files = fingerprint_patterns(paths.audit_globs)
    previous = load_snapshot(paths.audit_snapshot) if paths.audit_snapshot else {}
    return classify_audit(previous, files, ledger_text, mtime(paths.ledger))


# ── commands ─────────────────────────────────────────────────────────
def cmd_diagnose(args: argparse.Namespace) -> int:
    paths = _paths(args)
    now = _now(args)
    with _open_read(paths) as store:
        memories = store.iter_memories()
        try:
            user_max, bot_max = store.max_message_ids()
        except SchemaError:
            user_max = bot_max = None
    diagnosis = build_diagnosis(
        memories,
        state=_load_state(paths),
        audit=_run_audit(paths),
        now=now,
        user_max=user_max,
        bot_max=bot_max,
    )
    if args.json:
        _emit_json(diagnosis.to_dict())
    else:
        print(format_diagnosis(diagnosis))
    return 1 if args.strict and diagnosis.has_high() else 0


def cmd_orphan(args: argparse.Namespace) -> int:
    paths = _paths(args)
    state = _load_state(paths)
    with _open_read(paths) as store:
        memories = store.iter_memories()
    if state is None:
        print("ORPHAN_SKIP 尚无收尾记录，无法判定孤儿")
        return 0
    orphans = detect_orphans(memories, state.last_finish_ts, ORPHAN_MEMORY_TYPES)
    if args.json:
        _emit_json(
            {
                "last_finish_ts": state.last_finish_ts,
                "orphans": [
                    {
                        "memory_id": orphan.memory_id,
                        "memory_type": orphan.memory_type,
                        "importance": orphan.importance,
                        "created_at": orphan.created_at,
                    }
                    for orphan in orphans
                ],
            }
        )
        return 0
    if not orphans:
        print(
            "ORPHAN_NONE 无孤儿批次（上轮收尾 %s）" % _fmt_ts(state.last_finish_ts)
        )
        return 0
    print(
        "ORPHAN %d 条已写入但游标未推进（上轮收尾 %s）："
        % (len(orphans), _fmt_ts(state.last_finish_ts))
    )
    for orphan in orphans:
        print(
            "  #%s %s imp=%s 写入于 %s"
            % (
                orphan.memory_id,
                orphan.memory_type,
                orphan.importance,
                _fmt_ts(orphan.created_at),
            )
        )
    return 0


def _build_digest(store: SQLiteStore, state: PatrolState) -> dict[str, Any]:
    user_msgs = store.fetch_messages("raw_messages", state.last_user_msg_id, MAX_USER_MSGS)
    bot_msgs = store.fetch_messages("bot_messages", state.last_bot_msg_id, MAX_BOT_MSGS)
    user_max, _bot_max = store.max_message_ids()
    name_map = build_sender_name_map(store.sender_name_rows())

    events = []
    for row in user_msgs:
        events.append(
            (
                parse_ts(row["timestamp"]),
                0,
                display_sender(row, name_map),
                int(row["id"]),
                "user",
                str(row["message"]),
            )
        )
    for row in bot_msgs:
        events.append(
            (
                parse_ts(row["timestamp"]),
                1,
                "小鱼",
                int(row["id"]),
                "bot",
                str(row["message"]),
            )
        )
    events.sort(key=lambda event: (event[0], event[1]))

    lines: list[str] = []
    total = 0
    last_user_in = state.last_user_msg_id
    last_bot_in = state.last_bot_msg_id
    truncated = False
    for _timestamp, _order, who, message_id, source, message in events:
        text = "【%s】%s" % (who, message)
        if total + len(text) > MAX_CHARS:
            truncated = True
            break
        lines.append(text)
        total += len(text)
        if source == "user":
            last_user_in = max(last_user_in, message_id)
        else:
            last_bot_in = max(last_bot_in, message_id)

    return {
        "lines": lines,
        "user_msgs": len(user_msgs),
        "bot_msgs": len(bot_msgs),
        "last_user_in": last_user_in,
        "last_bot_in": last_bot_in,
        "has_more": (user_max - last_user_in) > 0,
        "truncated": truncated,
    }


def cmd_status(args: argparse.Namespace) -> int:
    paths = _paths(args)
    now = _now(args)
    state = _load_state(paths)
    with _open_read(paths) as store:
        user_max, bot_max = store.max_message_ids()
        cursor = state.last_user_msg_id if state is not None else user_max
        new_user = store.fetch_messages("raw_messages", cursor, MAX_USER_MSGS)
        decision = decide_status(
            state,
            user_max=user_max,
            bot_max=bot_max,
            new_user_count=len(new_user),
            now=now,
        )
        if decision.status == "FIRST":
            print("FIRST " + decision.reason)
            if args.apply:
                if paths.state is None:
                    print("ERROR --state is required to initialise the cursor")
                    return 2
                save_state(paths.state, initial_state(user_max, bot_max, now), backup_dir=paths.backups)
                print("STATE_SAVED=%s" % paths.state)
            else:
                print("(read-only: use --apply to initialise the cursor)")
            return 0

        if decision.status == "SKIP":
            print("SKIP " + decision.reason)
            return 0

        assert state is not None
        digest = _build_digest(store, state)

    print("WORK")
    print(decision.reason)
    print(
        "待提炼消息：raw_messages %d 条 / bot_messages %d 条（发送者已按真实名字标注）"
        % (digest["user_msgs"], digest["bot_msgs"])
    )
    print("BATCH_END_USER=%d" % digest["last_user_in"])
    print("BATCH_END_BOT=%d" % digest["last_bot_in"])
    print("HAS_MORE=%s" % ("true" if digest["has_more"] else "false"))
    if digest["truncated"]:
        print("TRUNCATED=true（摘要在上限 %d 字处截断）" % MAX_CHARS)
    print("---BEGIN---")
    print("\n".join(digest["lines"]))
    print("---END---")

    if args.apply:
        if paths.state is None:
            print("ERROR --state is required to persist pending boundaries")
            return 2
        state.pending_user_end = digest["last_user_in"]
        state.pending_bot_end = digest["last_bot_in"]
        save_state(paths.state, state, backup_dir=paths.backups)
        print("STATE_SAVED=%s" % paths.state)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    paths = _paths(args, require_db=False)
    if not paths.ledger or not paths.audit_globs:
        print("AUDIT_ERROR 需要 --ledger 与至少一个 --config GLOB")
        return 2
    ledger_text = read_text(paths.ledger)
    if ledger_text is None:
        print("AUDIT_ERROR 台账文件不存在：%s" % paths.ledger)
        return 2
    files = fingerprint_patterns(paths.audit_globs)
    previous = load_snapshot(paths.audit_snapshot) if paths.audit_snapshot else {}
    result = classify_audit(previous, files, ledger_text, mtime(paths.ledger))

    if args.json:
        _emit_json(
            {
                "ledger_missing": result.ledger_missing,
                "suspicious": [change.path for change in result.suspicious],
                "benign": [change.path for change in result.benign],
                "files": [state.path for state in files],
            }
        )
    elif result.suspicious:
        print("AUDIT_ALERT 发现疑似未留痕改动：")
        for change in result.suspicious:
            print("  %s" % change.path)
            print("    修改于 %s" % _fmt_ts(change.mtime))
        print("处置：把这几处补记进台账，并同步写一条记忆。")
    else:
        print("AUDIT_OK 全部受监控文件均不晚于台账，无未留痕改动")
    for change in result.benign:
        print("AUDIT_NOTE mtime 刷新但内容未变：%s @ %s" % (change.path, _fmt_ts(change.mtime)))

    if args.apply:
        if not paths.audit_snapshot:
            print("AUDIT_SNAPSHOT=missing --audit-snapshot")
            return 2
        if paths.audit_snapshot.exists():
            copy_file_backup(paths.audit_snapshot, paths.backups, tag="preaudit")
        save_snapshot(paths.audit_snapshot, result.snapshot)
        print("AUDIT_SNAPSHOT_SAVED=%s" % paths.audit_snapshot)
    return 1 if args.strict and result.suspicious else 0


def cmd_recall(args: argparse.Namespace) -> int:
    from .retrieval.context import recent_private_context
    from .retrieval.score import format_scored, recall_scored
    from .retrieval.store import load_rows

    paths = _paths(args)
    rows = load_rows(paths.db, as_of_ms=args.as_of_ms, schema=paths.schema)
    context = args.context or ""
    if not context and args.user_id:
        context = recent_private_context(
            paths.db,
            args.user_id,
            limit=4,
            schema=paths.schema,
            as_of_ts=(args.as_of_ms // 1000) if args.as_of_ms else None,
        )
    top_k = max(1, int(args.top_k))
    scored = recall_scored(
        args.query,
        rows=rows,
        context=context,
        group_id=args.group_id,
        user_id=args.user_id,
        top_k=top_k,
    )
    text = format_scored(scored[:top_k], max_chars=args.max_chars)
    if args.json:
        print(json.dumps({"query": args.query, "memory_ids": [item.row.id for item in scored[:top_k]], "text": text}, ensure_ascii=False))
    else:
        print(text or "(empty)")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    from .profiles import describe, list_profiles

    if args.list:
        for profile in list_profiles():
            print("%-8s %s" % (profile.name, profile.summary))
        return 0
    print(describe(args.name))
    return 0


def cmd_intents(args: argparse.Namespace) -> int:
    paths = _paths(args)
    now = _now(args)
    with _open_read(paths) as store:
        memories = store.iter_memories(["intent"])
    report = classify_intents(memories, datetime.date.fromtimestamp(now))
    updates = plan_intent_expiry(report)

    for row, due in report.pending:
        print("  #%s 到期 %s ｜%s" % (row.id, due, row.content[:70].replace("\n", " ")))
    for row in report.badfmt:
        print("  #%s 缺有效期（格式：【意图·有效期至 YYYY-MM-DD】）｜%s" % (row.id, row.content[:70]))
    print("INTENT_PENDING=%d" % len(report.pending))
    print("INTENT_EXPIRED=%s" % (",".join(str(update.memory_id) for update in updates) if updates else "0"))
    print("INTENT_BADFMT=%s" % (",".join(str(row.id) for row in report.badfmt) if report.badfmt else "0"))

    if args.apply:
        if not updates:
            print("APPLIED intents=0")
            return 0
        backup = backup_database(paths.db, paths.backups, tag="intents")
        print("DB_BACKUP=%s" % backup)
        with SQLiteStore(paths.db, readonly=False, schema=paths.schema) as store:
            store.require_schema()
            changed = store.apply_intent_updates(updates)
        print("APPLIED intents=%d" % changed)
    return 0


def cmd_decay(args: argparse.Namespace) -> int:
    paths = _paths(args)
    now = _now(args)
    with _open_read(paths) as store:
        memories = store.iter_memories()
    actions = plan_decay(memories, now)
    for action in actions:
        print(
            "  #%s %s imp=%d->%d%s"
            % (
                action.memory_id,
                action.memory_type,
                action.old_importance,
                action.new_importance,
                (" (%s)" % action.new_type) if action.new_type != action.memory_type else "",
            )
        )
    print("DECAY_CANDIDATES=%d" % len(actions))
    if args.apply:
        if not actions:
            print("APPLIED decay=0")
            return 0
        backup = backup_database(paths.db, paths.backups, tag="decay")
        print("DB_BACKUP=%s" % backup)
        with SQLiteStore(paths.db, readonly=False, schema=paths.schema) as store:
            store.require_schema()
            changed = store.apply_decay_actions(actions)
        print("APPLIED decay=%d" % changed)
    return 0


def _parse_mem_ids(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if raw == "none":
        return ["none"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def cmd_finish(args: argparse.Namespace) -> int:
    paths = _paths(args)
    now = _now(args)
    if args.user_end is None or args.bot_end is None:
        print("REFUSED 收尾被拒，游标未动：必须显式带 --user-end 与 --bot-end（照抄 status 的 BATCH_END_*）。")
        print("        不给边界的旧调用会一路推到 max，跨过本批没提炼的部分——那是漏账的老路。")
        return 3
    state = _load_state(paths) or PatrolState()
    with _open_read(paths) as store:
        user_max, bot_max = store.max_message_ids()
        mem_ids = _parse_mem_ids(args.mem_ids)
        numeric = []
        if mem_ids != ["none"]:
            for value in mem_ids:
                try:
                    numeric.append(int(value))
                except (TypeError, ValueError):
                    numeric.append(-1)
        lookup = store.memories_by_id([value for value in numeric if value >= 0]) if numeric else {}
    boundary_errors = []
    if args.user_end > user_max:
        boundary_errors.append("--user-end=%s 超出库内最大 user 消息 id %s" % (args.user_end, user_max))
    if args.bot_end > bot_max:
        boundary_errors.append("--bot-end=%s 超出库内最大 bot 消息 id %s" % (args.bot_end, bot_max))
    if args.user_end < state.last_user_msg_id or args.bot_end < state.last_bot_msg_id:
        boundary_errors.append("收尾边界会回退游标，拒绝（宁可重记，不可倒退）")
    if boundary_errors:
        print("REFUSED 收尾被拒，游标未动：")
        for error in boundary_errors:
            print("  - " + error)
        return 3

    ledger_text = read_text(paths.ledger)
    errors = verify_finish(
        mem_ids,
        args.ledger_mark,
        memories_by_id=lookup,
        ledger_text=ledger_text,
        prev_finish_ts=state.last_finish_ts,
        ledger_path=str(paths.ledger or "change_history.md"),
    )
    if errors:
        print("REFUSED 收尾被拒，游标未动（账没丢，补完再收尾）：")
        for error in errors:
            print("  - " + error)
        return 3
    if not args.apply:
        print("FINISH_READY 闸门通过（read-only：加 --apply 才推进游标）")
        return 0
    if paths.state is None:
        print("ERROR --state is required to advance the cursor")
        return 2
    new_state = advance_after_finish(
        state,
        user_end=args.user_end,
        bot_end=args.bot_end,
        user_max=user_max,
        now=now,
    )
    save_state(paths.state, new_state, backup_dir=paths.backups)
    if new_state.backfill:
        print(
            "OK 游标推进：user_id=%s, bot_id=%s（尚有 %s 条未消化，请立刻再跑一次 status）"
            % (new_state.last_user_msg_id, new_state.last_bot_msg_id, user_max - args.user_end)
        )
    else:
        print(
            "OK 游标推进：user_id=%s, bot_id=%s, 巡检时间已刷新"
            % (new_state.last_user_msg_id, new_state.last_bot_msg_id)
        )
    return 0


def cmd_consolidate(args: argparse.Namespace) -> int:
    paths = _paths(args)
    with _open_read(paths) as store:
        memories = store.iter_memories()
    if args.show:
        window = recent_episodic(memories)
        print(
            json.dumps(
                {
                    "window": len(window),
                    "candidates": [
                        {
                            "memory_id": memory.id,
                            "importance": memory.importance,
                            "content": memory.content,
                        }
                        for memory in window
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        with open(args.apply_file, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print("PLAN_ERROR 无法读取计划文件：%s" % exc)
        return 2
    promotions, errors = validate_plan(memories, plan)
    if errors:
        print("PLAN_ERROR 计划未通过校验：")
        for error in errors:
            print("  - " + error)
        return 2
    print("CONSOLIDATE_READY promotions=%d" % len(promotions))
    if not args.apply:
        return 0
    backup = backup_database(paths.db, paths.backups, tag="consolidate")
    print("DB_BACKUP=%s" % backup)
    with SQLiteStore(paths.db, readonly=False) as store:
        store.require_schema()
        changed = store.apply_promotions(promotions)
    print("APPLIED promotions=%d" % changed)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ConfigError, StoreError, StateError, SchemaError) as exc:
        print("ERROR %s: %s" % (type(exc).__name__, exc))
        return 4


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
