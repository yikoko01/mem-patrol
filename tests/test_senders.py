"""Port of production tests/test_sender_labels.py (11 checks) to pytest.

The bug: every raw_messages row was labelled "用户", so group members were folded
into the owner's voice. Labels are resolved per sender_id.
"""
from __future__ import annotations

from memorix.policy.senders import build_sender_name_map, display_sender

GROUP = "3AF8FB0F0CDF328982102635F711638C"
OWNER = "404BE32F7C9E448DB63AC9E0658A10EB"
NOODLE = "E35F513BCA3A00000000000000000001"


def row(**overrides):
    base = {
        "id": 0,
        "sender_id": "",
        "sender_name": "",
        "message": "",
        "group_id": GROUP,
        "timestamp": 0.0,
        "platform": "qq_official",
    }
    base.update(overrides)
    return base


def main_rows():
    return [
        row(id=1, sender_id=OWNER, sender_name="'尘风、", message="群里的我"),
        row(id=2, sender_id=OWNER, sender_name="", message="私聊里的我", group_id=OWNER),
        row(id=3, sender_id=NOODLE, sender_name="牛杂", message="群友发言"),
    ]


def end_rows():
    """Production test end-to-end fixture: owner, group member, private owner."""
    return [
        row(id=1, sender_id=OWNER, sender_name="'尘风、", message="我嘞"),
        row(id=2, sender_id=NOODLE, sender_name="牛杂", message="我嘞"),
        row(id=3, sender_id=OWNER, sender_name="", message="让我想想", group_id=OWNER),
    ]


def test_name_map_collects_owner():
    names = build_sender_name_map(main_rows())
    assert names.get(OWNER) == "'尘风、"


def test_name_map_collects_group_member():
    names = build_sender_name_map(main_rows())
    assert names.get(NOODLE) == "牛杂"


def test_row_name_wins():
    rows = main_rows()
    names = build_sender_name_map(rows)
    assert display_sender(rows[0], names) == "'尘风、"


def test_empty_name_is_backfilled_from_same_id():
    rows = main_rows()
    names = build_sender_name_map(rows)
    assert display_sender(rows[1], names) == "'尘风、"


def test_group_member_is_not_labelled_user():
    rows = main_rows()
    names = build_sender_name_map(rows)
    assert display_sender(rows[2], names) == "牛杂"


def test_private_chat_without_name_falls_back_to_user():
    rows = [row(id=1, sender_id=OWNER, group_id=OWNER)]
    assert display_sender(rows[0], {}) == "用户"


def test_group_without_name_uses_id_prefix():
    rows = [row(id=2, sender_id="ABCDEF123456")]
    assert display_sender(rows[0], {}) == "用户ABCDEF"


def test_none_name_map_does_not_crash():
    rows = [row(id=1, sender_id=OWNER, group_id=OWNER)]
    assert display_sender(rows[0], None) == "用户"


def test_end_to_end_two_distinct_labels():
    rows = end_rows()
    names = build_sender_name_map(rows)
    labels = [display_sender(r, names) for r in rows]
    assert sorted(set(labels)) == ["'尘风、", "牛杂"]


def test_same_text_different_people_stay_distinct():
    rows = end_rows()
    names = build_sender_name_map(rows)
    labels = [display_sender(r, names) for r in rows]
    assert labels[0] != labels[1]


def test_private_row_maps_to_the_owner():
    rows = end_rows()
    names = build_sender_name_map(rows)
    labels = [display_sender(r, names) for r in rows]
    assert labels[2] == labels[0]
