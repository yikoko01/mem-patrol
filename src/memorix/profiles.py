"""Use-case presets: chat bot vs long-term project vs both (M4.1).

A profile is only a set of **defaults** and an MCP tool allow-list — it never
locks behaviour. Explicit call-site arguments and config keys always win
(``merge_config`` ordering: profile defaults < explicit config). Safety
invariants are deliberately NOT switchable: MCP is read-only, repairs need
``--apply`` with a backup, recall separates query/instruction, and contracts are
never pulled without an anchor.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Profile:
    name: str
    title: str
    summary: str
    features: Mapping[str, bool] = field(default_factory=dict)
    mcp_tools: tuple[str, ...] = ()
    config_defaults: Mapping[str, Any] = field(default_factory=dict)


_ALL_TOOLS = (
    "memorix_diagnose",
    "memorix_orphan",
    "memorix_recall",
    "memorix_gate_check",
    "memorix_judge_replay",
    "memorix_eval",
)

PROFILES: dict[str, Profile] = {
    "chat": Profile(
        name="chat",
        title="聊天机器人",
        summary="召回 + 判官闸门 + 影子/审查者；不跑巡检与记忆整理写操作。",
        features={"recall": True, "gatekeep": True, "patrol": False, "eval": False, "metrics": True, "safety": True},
        mcp_tools=("memorix_recall", "memorix_gate_check", "memorix_judge_replay"),
        config_defaults={
            "enable_group_interjection": True,
            "group_interject_max_daily": 30,
            "group_interject_judge_decides": True,
            "group_interject_judge_min_consult_seconds": 10,
            "group_interject_min_interval_minutes": 1,
            "group_interject_same_topic_cooldown_minutes": 0,
            "group_busy_timing_enabled": True,
        },
    ),
    "project": Profile(
        name="project",
        title="长期项目",
        summary="巡检诊断/记忆卫生/离线评测；不启用群聊插话裁判。",
        features={"recall": True, "gatekeep": False, "patrol": True, "eval": True, "metrics": True, "safety": True},
        mcp_tools=("memorix_diagnose", "memorix_orphan", "memorix_recall", "memorix_eval"),
        config_defaults={
            "enable_group_interjection": False,
            "group_interject_max_daily": 0,
        },
    ),
    "both": Profile(
        name="both",
        title="聊天 + 长期项目",
        summary="两个内核同时可用；判定优先、轻节流（聊天会说话，项目面照常诊断）。",
        features={"recall": True, "gatekeep": True, "patrol": True, "eval": True, "metrics": True, "safety": True},
        mcp_tools=_ALL_TOOLS,
        config_defaults={
            "enable_group_interjection": True,
            "group_interject_max_daily": 30,
            "group_interject_judge_decides": True,
            "group_interject_judge_min_consult_seconds": 10,
            "group_interject_min_interval_minutes": 1,
        },
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[str(name)]
    except KeyError as exc:
        raise ValueError("unknown profile %r (choose chat/project/both)" % name) from exc


def list_profiles() -> list[Profile]:
    return [PROFILES[name] for name in ("chat", "project", "both")]


def tools_for(profile: str | Profile) -> tuple[str, ...]:
    return (get_profile(profile) if isinstance(profile, str) else profile).mcp_tools


def merge_config(profile: str | Profile, config: Mapping[str, Any] | None = None) -> dict:
    """Profile defaults first, explicit config wins (never the reverse)."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    merged = dict(resolved.config_defaults)
    merged.update(dict(config or {}))
    return merged


def describe(profile: str | Profile) -> str:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    enabled = [name for name, on in resolved.features.items() if on]
    disabled = [name for name, on in resolved.features.items() if not on]
    lines = [
        "PROFILE=%s · %s" % (resolved.name, resolved.title),
        "summary=%s" % resolved.summary,
        "features_on=%s" % ",".join(enabled),
        "features_off=%s" % (",".join(disabled) or "-"),
        "mcp_tools=%s" % ",".join(resolved.mcp_tools),
    ]
    for key, value in sorted(resolved.config_defaults.items()):
        lines.append("config.%s=%s" % (key, value))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.profiles")
    parser.add_argument("--name", default="both", help="chat / project / both")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        profiles = list_profiles()
        if args.json:
            print(json.dumps([profile.__dict__ for profile in profiles], ensure_ascii=False, indent=2))
        else:
            for profile in profiles:
                print("%-8s %s" % (profile.name, profile.summary))
        return 0
    if args.json:
        print(json.dumps(get_profile(args.name).__dict__, ensure_ascii=False, indent=2))
    else:
        print(describe(args.name))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
