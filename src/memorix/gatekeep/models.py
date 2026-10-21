"""gatekeep data contracts (pure data, no IO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Decision:
    """The production return shape: ``(should_reply, reply, reason, needs_tools)``.

    There is deliberately **no ``confidence``** field: the production judge never
    emitted one (verified 2026-10-21), so adding one here would be inventing API.
    """

    allow: bool = False
    text: str = ""
    reason: str = ""
    needs_tools: bool = False


@dataclass(frozen=True)
class GateResult:
    """One gate's verdict. ``weight`` lets soft gates down-weight without vetoing."""

    allowed: bool
    reason: str = ""
    weight: float = 1.0
    wait_seconds: int = 0


@dataclass(frozen=True)
class Context:
    """The minimal, IM-agnostic context a decision needs (guide §6 decision #4)."""

    text: str
    group_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    message_id: str = ""
    timestamp: float = 0.0
    quoted_text: str = ""
    directed: bool = False
    addressed_to_bot: bool = False  # @/reply/name addressed to the bot but not via directed path
    scene_trigger: str = ""
    talking_to: str = ""
    talking_to_source: str = ""
    talking_to_confidence: float = 0.0
    memory_context: str = ""
    group: Mapping[str, Any] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateTrace:
    gate: str
    result: GateResult


@dataclass(frozen=True)
class Outcome:
    """What the pipeline decided to do with this trigger."""

    action: str  # sent / dropped / handoff / tool_task / candidate
    decision: Decision
    reason: str = ""
    trace: tuple[GateTrace, ...] = ()
