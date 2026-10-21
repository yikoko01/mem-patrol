"""Patrol cursor state: pure status decision + atomic persistence."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .store import copy_file_backup

COOLDOWN_SECONDS = 6 * 3600
MIN_NEW_MESSAGES = 10
MAX_USER_MSGS = 60
MAX_BOT_MSGS = 60
MAX_CHARS = 8000


class StateError(RuntimeError):
    """State file is unreadable or has the wrong shape."""


@dataclass
class PatrolState:
    last_run_ts: int = 0
    last_user_msg_id: int = 0
    last_bot_msg_id: int = 0
    backfill: bool = False
    last_finish_ts: int = 0
    pending_user_end: int | None = None
    pending_bot_end: int | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PatrolState":
        def _int(key: str) -> int:
            try:
                return int(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0

        def _opt_int(key: str) -> int | None:
            value = data.get(key)
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return cls(
            last_run_ts=_int("last_run_ts"),
            last_user_msg_id=_int("last_user_msg_id"),
            last_bot_msg_id=_int("last_bot_msg_id"),
            backfill=bool(data.get("backfill", False)),
            last_finish_ts=_int("last_finish_ts"),
            pending_user_end=_opt_int("pending_user_end"),
            pending_bot_end=_opt_int("pending_bot_end"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_run_ts": self.last_run_ts,
            "last_user_msg_id": self.last_user_msg_id,
            "last_bot_msg_id": self.last_bot_msg_id,
            "backfill": self.backfill,
            "last_finish_ts": self.last_finish_ts,
            "pending_user_end": self.pending_user_end,
            "pending_bot_end": self.pending_bot_end,
        }


@dataclass(frozen=True)
class StatusDecision:
    """Result of the pure status gate."""

    status: str  # FIRST / SKIP / WORK
    reason: str
    backlog: bool = False


def decide_status(
    state: PatrolState | None,
    *,
    user_max: int,
    bot_max: int,
    new_user_count: int,
    now: int,
    cooldown_seconds: int = COOLDOWN_SECONDS,
    min_new_messages: int = MIN_NEW_MESSAGES,
    max_user_msgs: int = MAX_USER_MSGS,
) -> StatusDecision:
    """Port of the production status gate (first-run / cooldown / backlog)."""
    if state is None:
        return StatusDecision("FIRST", "首次初始化：游标将设到当前消息", backlog=False)
    backlog = (int(user_max) - state.last_user_msg_id) > int(max_user_msgs) or bool(
        state.backfill
    )
    if not backlog:
        since = int(now) - state.last_run_ts
        if since < cooldown_seconds:
            return StatusDecision(
                "SKIP",
                "冷却中：距上次巡检 %d 分钟，需满 %d 小时"
                % (since // 60, cooldown_seconds // 3600),
                backlog=False,
            )
        if new_user_count < min_new_messages:
            return StatusDecision(
                "SKIP",
                "消息太少：新用户消息仅 %d 条，需 >= %d"
                % (new_user_count, min_new_messages),
                backlog=False,
            )
    reason = "补账模式：检测到积压，本次跳过冷却直接开工" if backlog else "达到巡检条件"
    return StatusDecision("WORK", reason, backlog=backlog)


def initial_state(user_max: int, bot_max: int, now: int) -> PatrolState:
    return PatrolState(last_run_ts=int(now), last_user_msg_id=int(user_max), last_bot_msg_id=int(bot_max))


def advance_after_finish(
    state: PatrolState,
    *,
    user_end: int,
    bot_end: int,
    user_max: int,
    now: int,
) -> PatrolState:
    """Port of the production finish cursor advance (backfill aware)."""
    remaining = int(user_max) - int(user_end)
    backfill = remaining > 0
    last_run_ts = state.last_run_ts if backfill else int(now)
    return PatrolState(
        last_run_ts=last_run_ts,
        last_user_msg_id=int(user_end),
        last_bot_msg_id=int(bot_end),
        backfill=backfill,
        last_finish_ts=int(now),
    )


def load_state(path: str | Path | None) -> PatrolState | None:
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError("unreadable state file %s: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise StateError("state file %s must contain a JSON object" % path)
    return PatrolState.from_mapping(data)


def save_state(
    path: str | Path,
    state: PatrolState,
    *,
    backup_dir: str | Path | None = None,
) -> None:
    """Atomic write (tmp + os.replace); optional pre-write backup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup_dir is not None:
        copy_file_backup(path, backup_dir, tag="preapply")
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
