"""Filesystem IO for the audit snapshot (the only IO module in M0).

Discovery + md5 + JSON snapshot live here; the comparison itself is pure and
lives in :mod:`memorix.policy.audit`.
"""
from __future__ import annotations

import glob as _glob
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

from ..models import FileState

__all__ = [
    "fingerprint_file",
    "fingerprint_patterns",
    "load_snapshot",
    "save_snapshot",
]


def fingerprint_file(path: str) -> FileState:
    """md5 + mtime for one file (raises OSError if unreadable)."""
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return FileState(path=path, md5=digest.hexdigest(), mtime=os.path.getmtime(path))


def fingerprint_patterns(patterns: Iterable[str]) -> list[FileState]:
    """Expand glob patterns into deduplicated, real-path file fingerprints.

    Unreadable files are skipped (production does the same per-file).
    """
    states: list[FileState] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in _glob.glob(pattern):
            real = os.path.realpath(path)
            if real in seen or not os.path.isfile(real):
                continue
            seen.add(real)
            try:
                states.append(fingerprint_file(real))
            except OSError:
                continue
    return states


def load_snapshot(path: str | Path) -> dict[str, str]:
    """Load the acknowledged snapshot; corrupt or missing -> empty dict."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_snapshot(path: str | Path, snapshot: Mapping[str, str]) -> None:
    """Atomically persist the snapshot (tmp + os.replace)."""
    path = str(path)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporary, path)
