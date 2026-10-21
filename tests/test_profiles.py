"""M4.1 use-case presets: chat / project / both (defaults + tool allow-list)."""
from __future__ import annotations

import json

import pytest

from memorix.profiles import (
    PROFILES,
    describe,
    get_profile,
    list_profiles,
    main as profiles_main,
    merge_config,
    tools_for,
)


def test_profile_names_and_order():
    assert [profile.name for profile in list_profiles()] == ["chat", "project", "both"]
    assert set(PROFILES) == {"chat", "project", "both"}


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        get_profile("nope")


def test_feature_flags():
    chat = get_profile("chat")
    project = get_profile("project")
    both = get_profile("both")
    assert chat.features["gatekeep"] and not chat.features["patrol"]
    assert project.features["patrol"] and not project.features["gatekeep"]
    assert all(both.features.values())


def test_tool_allow_lists():
    assert len(tools_for("chat")) == 3
    assert len(tools_for("project")) == 4
    assert len(tools_for("both")) == 6
    assert "memorix_gate_check" in tools_for("chat")
    assert "memorix_diagnose" not in tools_for("chat")
    assert "memorix_diagnose" in tools_for("project")
    assert "memorix_gate_check" not in tools_for("project")


def test_merge_config_explicit_wins():
    merged = merge_config("chat", {"group_interject_max_daily": 99, "enable_group_interjection": False})
    assert merged["group_interject_max_daily"] == 99
    assert merged["enable_group_interjection"] is False
    assert merged["group_interject_judge_min_consult_seconds"] == 10


def test_describe_and_cli():
    text = describe("chat")
    assert "PROFILE=chat" in text and "mcp_tools=memorix_recall" in text
    assert profiles_main(["--name", "project"]) == 0
    assert profiles_main(["--list"]) == 0


def test_cli_json():
    assert profiles_main(["--name", "both", "--json"]) == 0


def test_interjection_defaults_are_conversational():
    chat = merge_config("chat")
    both = merge_config("both")
    project = merge_config("project")
    assert chat["enable_group_interjection"] is True
    assert both["enable_group_interjection"] is True
    assert project["enable_group_interjection"] is False
    assert 0 < chat["group_interject_judge_min_consult_seconds"] <= 30
    # User preference: more active than production handoff (20/day, 15min warmth).
    assert chat["group_interject_max_daily"] == 30
    assert chat["group_interject_min_interval_minutes"] == 1
    assert both["group_interject_max_daily"] == 30
    assert both["group_interject_min_interval_minutes"] == 1
