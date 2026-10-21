"""gatekeep (M2): a host-agnostic decision kernel extracted from the group judge.

No IM types, no plugin instance, no database, no network. The host supplies a
``Context`` and an optional ``judge`` callable; this package owns the
deterministic gates, the JSON decision contract, the needs-tools routing and
the shadow/precision bookkeeping.
"""
from .decide import decide, parse_decision, parse_needs_tools
from .gates import default_gates, relative_budget, stable_roll
from .models import Context, Decision, GateResult, Outcome
from .shadow import ShadowBook

__all__ = [
    "Context",
    "Decision",
    "GateResult",
    "Outcome",
    "ShadowBook",
    "decide",
    "default_gates",
    "parse_decision",
    "parse_needs_tools",
    "relative_budget",
    "stable_roll",
]
