"""Pluggable reviewers (pure functions; hosts decide what to do with flags)."""
from .premature_promise import barren_phrase, flags_for as premature_flags
from .retrieval_witness import absence_claim, flags_for as retrieval_flags, turn_had_retrieval

__all__ = [
    "barren_phrase",
    "premature_flags",
    "absence_claim",
    "retrieval_flags",
    "turn_had_retrieval",
]
