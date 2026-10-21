"""Load prompt assets from ``gatekeep/prompts/`` (files are data, not code)."""
from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).with_name("prompts")


def load_prompt(name: str = "decision.md") -> str:
    path = _PROMPT_DIR / name
    if not path.is_file():
        raise FileNotFoundError("prompt not found: %s" % path)
    return path.read_text(encoding="utf-8")


def prompt_placeholders(name: str = "decision.md") -> set[str]:
    """The ``{placeholder}`` names a prompt expects (for adapter/render tests)."""
    import re

    return set(re.findall(r"\{([a-z_][a-z0-9_]*)\}", load_prompt(name)))
