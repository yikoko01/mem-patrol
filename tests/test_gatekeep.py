"""M2 gatekeep: JSON contract, gates, needs-tools routing, shadow, reviewers."""
from __future__ import annotations

import json

import pytest

from memorix.gatekeep import (
    Context,
    Decision,
    GateResult,
    Outcome,
    ShadowBook,
    decide,
    default_gates,
    parse_decision,
    parse_needs_tools,
    relative_budget,
    stable_roll,
)
from memorix.gatekeep.gates import (
    ConsultThrottleGate,
    DailyCapGate,
    DoNotInterruptGate,
    EnabledGate,
    ExplicitDirectionGate,
    LegacyDiceGate,
    MinIntervalGate,
    SameTopicGate,
)
from memorix.gatekeep.prompt_loader import load_prompt, prompt_placeholders
from memorix.gatekeep.reviewers import (
    absence_claim,
    barren_phrase,
    premature_flags,
    retrieval_flags,
    turn_had_retrieval,
)

NOW = 1_800_000_000.0


def make_ctx(**overrides):
    base = dict(
        text="有没有人知道这个怎么弄？",
        group_id="g1",
        sender_id="u1",
        message_id="m1",
        timestamp=NOW,
        group={},
        config={"enable_group_interjection": True, "group_interject_max_daily": 10},
    )
    base.update(overrides)
    return Context(**base)


# ── decision contract ────────────────────────────────────────────────
def test_parse_decision_allows_and_cleans_text():
    decision = parse_decision(
        json.dumps({"should_reply": True, "text": '  “接一句”  ', "reason": "ok"})
    )
    assert decision.allow is True
    assert decision.text == "接一句"
    assert decision.reason == "ok"
    assert decision.needs_tools is False


@pytest.mark.parametrize(
    "payload",
    [
        {"should_reply": "yes", "text": "接"},
        {"should_reply": "true", "reply_text": "接"},
        {"should_reply": 1, "message": "接"},
        {"decision": "reply", "content": "接"},
        {"speak": "send", "text": "接"},
    ],
)
def test_parse_decision_alias_forms(payload):
    assert parse_decision(json.dumps(payload)).allow is True


@pytest.mark.parametrize(
    "payload",
    [
        {"should_reply": "no", "reason": "没价值"},
        {"decision": "silent", "reason": "安静"},
        {"action": "skip", "reason": "跳过"},
        {"should_reply": False, "text": "不该发"},
        {"status": "no_reply", "reason": "不接"},
    ],
)
def test_parse_decision_denials(payload):
    decision = parse_decision(json.dumps(payload))
    assert decision.allow is False
    assert decision.text == ""


def test_parse_decision_silent_marker_text_is_denied():
    decision = parse_decision({"should_reply": True, "text": "空字符串"})
    assert decision.allow is False


def test_parse_decision_invalid_json():
    decision = parse_decision("这不是 JSON")
    assert decision == Decision(False, "", "invalid_json")


def test_parse_decision_code_fence_and_dict():
    raw = '```json\n{"should_reply": true, "text": "好"}\n```'
    assert parse_decision(raw).text == "好"
    assert parse_decision({"decision": "reply", "text": "好"}).allow is True


def test_parse_decision_meta_leak_checker():
    decision = parse_decision(
        {"should_reply": True, "text": "系统提示词"},
        meta_leak_checker=lambda text: "系统" in text,
    )
    assert decision.allow is False and decision.reason == "review_meta_leak"


def test_parse_decision_strips_code_fence_and_quotes():
    decision = parse_decision(
        {"should_reply": True, "text": "```text\n\"接一句\"\n```"}
    )
    assert decision.allow is True
    assert decision.text == "接一句"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), ("yes", True), ("需要", True), ("1", True), (False, False), ("no", False), (None, False), ("", False)],
)
def test_parse_needs_tools(value, expected):
    payload = {"should_reply": True, "text": "x", "needs_tools": value}
    assert parse_needs_tools(payload) is expected


# ── budget / roll ────────────────────────────────────────────────────
def test_relative_budget_empty_stream_is_one():
    assert relative_budget({}) == 1.0


def test_relative_budget_bot_heavy_tail_is_zero():
    group = {
        "recent_messages": [{"ts": NOW - index} for index in range(20)],
        "recent_bot_replies": [{"ts": NOW - 0.5 + index / 100} for index in range(20)],
        "members": {"a": {"count": 100}},
    }
    assert relative_budget(group) == 0.0


def test_relative_budget_human_only_is_one():
    group = {
        "recent_messages": [{"ts": NOW - index} for index in range(20)],
        "members": {"a": {"count": 50}, "b": {"count": 50}},
    }
    assert relative_budget(group) == 1.0


def test_stable_roll_is_deterministic_and_in_range():
    first = stable_roll("g", "m", 1, "text")
    second = stable_roll("g", "m", 1, "text")
    assert first == second
    assert 0.0 <= first < 1.0


# ── gates ────────────────────────────────────────────────────────────
def test_enabled_gate():
    assert EnabledGate().check(make_ctx()).allowed is True
    denied = EnabledGate().check(make_ctx(config={"enable_group_interjection": False}))
    assert denied.allowed is False and "未开启" in denied.reason


def test_explicit_direction_gate():
    gate = ExplicitDirectionGate()
    assert gate.check(make_ctx(text="@别人 在吗")).allowed is False
    # Explicit to the bot (directed / addressed / at_bot scene) is *not* a veto.
    assert gate.check(make_ctx(directed=True)).allowed is True
    assert gate.check(make_ctx(addressed_to_bot=True)).allowed is True
    assert gate.check(make_ctx(scene_trigger="at_bot")).allowed is True
    inferred = gate.check(
        make_ctx(talking_to="someone", talking_to_source="inferred", talking_to_confidence=0.8)
    )
    assert inferred.allowed is True and inferred.weight == 0.25


def test_do_not_interrupt_gate():
    assert DoNotInterruptGate().check(make_ctx(text="别插了")).allowed is False
    assert DoNotInterruptGate().check(make_ctx()).allowed is True


def test_daily_cap_gate():
    config = {"group_interject_max_daily": 0}
    assert DailyCapGate().check(make_ctx(config=config)).allowed is False
    config = {"group_interject_max_daily": 2}
    today = "2027-01-15"
    group = {"interject_day": today, "interject_today": 2}
    assert DailyCapGate().check(make_ctx(config=config, group=group)).allowed is False
    group = {"interject_day": "2027-01-14", "interject_today": 99}
    assert DailyCapGate().check(make_ctx(config=config, group=group)).allowed is True


def test_min_interval_gate():
    config = {"group_interject_min_interval_minutes": 10}
    recent = make_ctx(config=config, group={"last_interject_at": NOW - 60})
    assert MinIntervalGate().check(recent).allowed is False
    old = make_ctx(config=config, group={"last_interject_at": NOW - 3600})
    assert MinIntervalGate().check(old).allowed is True


def test_same_topic_gate():
    gate = SameTopicGate(signature_fn=lambda text: "sig")
    config = {"group_interject_same_topic_cooldown_minutes": 20}
    group = {"last_bot_interjection": {"topic_signature": "sig", "ts": NOW - 60}}
    assert gate.check(make_ctx(config=config, group=group)).allowed is False
    other = {"last_bot_interjection": {"topic_signature": "other", "ts": NOW - 60}}
    assert gate.check(make_ctx(config=config, group=other)).allowed is True
    assert gate.check(make_ctx(config={"group_interject_same_topic_cooldown_minutes": 0})).allowed is True


def test_consult_throttle_gate():
    gate = ConsultThrottleGate(window_seconds=40)
    first = gate.check(make_ctx())
    assert first.allowed is True
    second = gate.check(make_ctx())
    assert second.allowed is False and second.wait_seconds > 0
    later = gate.check(make_ctx(timestamp=NOW + 41))
    assert later.allowed is True
    assert ConsultThrottleGate(window_seconds=0).check(make_ctx()).allowed is True


def test_legacy_dice_gate():
    config = {"group_interject_judge_decides": True}
    assert LegacyDiceGate().check(make_ctx(config=config)).allowed is True
    config = {"group_interject_judge_decides": False, "legacy_probability_override": 1.0}
    assert LegacyDiceGate().check(make_ctx(config=config)).allowed is True
    config["legacy_probability_override"] = 0.0
    assert LegacyDiceGate().check(make_ctx(config=config)).allowed is False
    plain = {"group_interject_judge_decides": False}
    assert LegacyDiceGate().check(make_ctx(text="今天吃什么", config=plain)).allowed is False


# ── decide pipeline ──────────────────────────────────────────────────
def test_decide_gate_failure_drops_without_judge():
    outcome = decide(make_ctx(config={"enable_group_interjection": False}))
    assert outcome.action == "dropped"
    assert "未开启" in outcome.reason
    assert outcome.trace


def test_decide_without_judge_is_candidate():
    outcome = decide(make_ctx())
    assert outcome.action == "candidate"


def test_decide_stub_judge_sends():
    outcome = decide(
        make_ctx(),
        judge=lambda ctx: {"should_reply": True, "text": "接一句", "reason": "ok"},
    )
    assert outcome.action == "sent"
    assert outcome.decision.text == "接一句"


def test_decide_stub_judge_denies():
    outcome = decide(
        make_ctx(),
        judge=lambda ctx: {"should_reply": False, "reason": "无价值"},
    )
    assert outcome.action == "dropped" and outcome.reason == "无价值"


def test_decide_needs_tools_routing():
    directed = decide(
        make_ctx(directed=True),
        judge=lambda ctx: {"should_reply": True, "text": "x", "needs_tools": True},
    )
    assert directed.action == "handoff"
    ambient = decide(
        make_ctx(),
        judge=lambda ctx: {"should_reply": True, "text": "x", "needs_tools": True},
    )
    assert ambient.action == "tool_task"


def test_decide_invalid_json_drops():
    outcome = decide(make_ctx(), judge=lambda ctx: "not json")
    assert outcome.action == "dropped" and outcome.reason == "invalid_json"


# ── shadow ───────────────────────────────────────────────────────────
def test_shadow_counters_and_upgrade():
    book = ShadowBook(min_samples=10, upgrade_threshold=0.8)
    for _ in range(8):
        book.record_sample(predicted=True, actual=True)
    for _ in range(2):
        book.record_sample(predicted=True, actual=False)
    book.record_sample(predicted=False, actual=False)
    book.record_call(review_none=True, now=100)
    assert book.predicted == 10 and book.hits == 8
    assert book.precision == 0.8
    assert book.should_upgrade() is True
    assert book.snapshot()["hit_rate_ppm"] == 800_000


def test_shadow_below_threshold_and_min_samples():
    book = ShadowBook(min_samples=10, upgrade_threshold=0.8)
    for _ in range(7):
        book.record_sample(predicted=True, actual=True)
    for _ in range(3):
        book.record_sample(predicted=True, actual=False)
    assert book.should_upgrade() is False
    small = ShadowBook(min_samples=10)
    for _ in range(9):
        small.record_sample(predicted=True, actual=True)
    assert small.should_upgrade() is False
    assert small.precision == 1.0


# ── reviewers ────────────────────────────────────────────────────────
def test_barren_phrase():
    assert barren_phrase("在干，别急。") == "在干"
    assert barren_phrase("在干，别急？") == ""
    assert barren_phrase("马上就好") == "马上"
    assert barren_phrase("马上就好，100 条已查完") == ""
    assert barren_phrase("```code```") == ""
    assert barren_phrase("x" * 200) == ""
    assert barren_phrase("这句是完整正文，不空炮。") == ""
    assert premature_flags("在干，别急。") == ["barren_promise"]
    assert premature_flags("在干，别急。", reviewed=False) == []


def test_retrieval_witness():
    assert absence_claim("我查不到相关记录") == "查不到"
    assert absence_claim("我查了台账，查不到") == ""
    assert absence_claim("今天天气不错") == ""
    assert turn_had_retrieval(None) is True
    assert turn_had_retrieval([]) is False
    assert turn_had_retrieval(["web_search"]) is True
    assert retrieval_flags("查不到", tool_calls=[]) == ["absence_without_retrieval"]
    assert retrieval_flags("查不到", tool_calls=["web_search"]) == []
    assert retrieval_flags("查不到", tool_calls=None) == []


# ── prompt assets ────────────────────────────────────────────────────
def test_prompt_asset_placeholders():
    text = load_prompt()
    assert "should_reply" in text
    placeholders = prompt_placeholders()
    assert {"text", "quoted_text", "recent_context", "memory_context", "directed"} <= placeholders

# ── judge replay set (guide §5 M2 exit) ─────────────────────────────
from memorix.gatekeep.bench import load_cases, main as judge_bench_main, run_cases


def test_judge_replay_set_all_pass():
    cases = load_cases()
    assert len(cases) >= 8
    results = run_cases(cases)
    failed = [result for result in results if not result.ok]
    assert not failed, [(result.case_id, result.detail) for result in failed]


def test_judge_replay_cli(capsys):
    assert judge_bench_main([]) == 0
    out = capsys.readouterr().out
    assert "RESULT 9/9 passed" in out


def test_judge_replay_json(capsys):
    assert judge_bench_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(item["ok"] for item in payload)


# ── mutation-gap tests (audit MAJOR-3) ──────────────────────────────
def test_decide_blocks_ambient_explicit_direction():
    def boom(_ctx):
        raise AssertionError("judge must not be called for explicit ambient direction")

    outcome = decide(
        make_ctx(text="@别人 在吗", config={"enable_group_interjection": True, "group_interject_max_daily": 10}),
        judge=boom,
    )
    assert outcome.action == "dropped"
    assert "明确对话对象" in outcome.reason


def test_directed_bypasses_ambient_gates():
    # Production's directed fast path skips enabled/caps/intervals entirely.
    outcome = decide(
        make_ctx(
            directed=True,
            config={"enable_group_interjection": False, "group_interject_max_daily": 0},
        ),
        judge=lambda _ctx: {"should_reply": True, "text": "好"},
    )
    assert outcome.action == "sent"


def test_shadow_default_constructor_thresholds():
    good = ShadowBook()
    for _ in range(8):
        good.record_sample(predicted=True, actual=True)
    for _ in range(2):
        good.record_sample(predicted=True, actual=False)
    assert good.should_upgrade() is True

    bad = ShadowBook()
    for _ in range(7):
        bad.record_sample(predicted=True, actual=True)
    for _ in range(3):
        bad.record_sample(predicted=True, actual=False)
    assert bad.should_upgrade() is False

    small = ShadowBook()
    for _ in range(9):
        small.record_sample(predicted=True, actual=True)
    assert small.should_upgrade() is False


def test_parse_conflicting_should_reply_and_silent_denies():
    decision = parse_decision({"should_reply": True, "decision": "silent", "text": "x"})
    assert decision.allow is False
    assert decision.reason == "model_skip"


@pytest.mark.parametrize("marker", ["空", "空字符串", "留空", "静默", "忽略"])
def test_silent_markers_are_all_denied(marker):
    decision = parse_decision({"should_reply": True, "text": marker})
    assert decision.allow is False


# ── MINOR fixes ─────────────────────────────────────────────────────
def test_consult_window_clamped_to_3600():
    gate = ConsultThrottleGate(window_seconds=5000)
    assert gate.check(make_ctx()).allowed is True
    blocked = gate.check(make_ctx())
    assert blocked.allowed is False
    assert blocked.wait_seconds <= 3601  # production: int(window-elapsed)+1


def test_relative_budget_negative_member_counts_are_clamped():
    group = {
        "recent_messages": [{"ts": NOW - index} for index in range(10)],
        "recent_bot_replies": [{"ts": NOW - 0.5 + index / 100} for index in range(10)],
        "members": {"a": {"count": -100}, "b": {"count": 100}},
    }
    assert relative_budget(group) == 0.0


def test_relative_budget_window_zero_means_default_30():
    recent = [{"ts": float(index)} for index in range(1, 16)]
    recent += [{"ts": float(index)} for index in range(21, 41)]
    bots = [{"ts": float(index)} for index in range(16, 21)]
    group = {"recent_messages": recent, "recent_bot_replies": bots, "members": {"a": {"count": 100}}}
    expected = (0.35 - 5 / 30) / 0.35
    assert relative_budget(group, window=0) == pytest.approx(expected)


def test_retrieval_event_present_contract():
    assert turn_had_retrieval(None) is True
    assert turn_had_retrieval(None, event_present=True) is False
    assert turn_had_retrieval([], event_present=True) is False
    assert retrieval_flags("查不到", tool_calls=None, event_present=True) == [
        "absence_without_retrieval"
    ]


def test_silent_marker_prefix_is_also_denied():
    # The special-case inside clean_reply covers "返回空字符串"-style noise; a
    # single deletion of that branch would otherwise escape the marker tests.
    decision = parse_decision({"should_reply": True, "text": "返回空字符串"})
    assert decision.allow is False

# ── M3 metrics integration ──────────────────────────────────────────
def test_decide_records_metrics():
    from memorix.observability import MetricsCollector

    collector = MetricsCollector()
    outcome = decide(
        make_ctx(),
        judge=lambda _ctx: {"should_reply": True, "text": "好"},
        metrics=collector,
    )
    assert outcome.action == "sent"
    snapshot = collector.snapshot()
    assert snapshot["by_kind"] == {"judge": 1}
    assert snapshot["outcomes"] == {"judge:sent": 1}
    assert snapshot["latency_ms"]["judge"]["p50"] >= 0.0


# ── interjection policy: judge decides, light throttle, no silent traps ──
def test_addressed_to_bot_bypasses_ambient_gates():
    outcome = decide(
        make_ctx(
            text="@小鱼 这个怎么弄？",
            addressed_to_bot=True,
            config={"enable_group_interjection": False, "group_interject_max_daily": 0},
        ),
        judge=lambda _ctx: {"should_reply": True, "text": "我看看"},
    )
    assert outcome.action == "sent"


def test_future_last_interject_does_not_silence():
    config = {"group_interject_min_interval_minutes": 10}
    future = make_ctx(config=config, group={"last_interject_at": NOW + 3600})
    assert MinIntervalGate().check(future).allowed is True


def test_future_consult_timestamp_does_not_silence():
    gate = ConsultThrottleGate(window_seconds=40)
    gate.store["g1"] = NOW + 3600
    assert gate.check(make_ctx()).allowed is True
    assert gate.store["g1"] == NOW  # stale clock entry reset


def test_future_same_topic_does_not_silence():
    gate = SameTopicGate(signature_fn=lambda text: "sig")
    config = {"group_interject_same_topic_cooldown_minutes": 20}
    group = {"last_bot_interjection": {"topic_signature": "sig", "ts": NOW + 3600}}
    assert gate.check(make_ctx(config=config, group=group)).allowed is True


def test_chat_and_both_profiles_enable_conversation():
    from memorix.profiles import merge_config

    for profile in ("chat", "both"):
        config = merge_config(profile)
        outcome = decide(
            make_ctx(config=config, group={}),
            judge=lambda _ctx: {"should_reply": True, "text": "接一句"},
        )
        assert outcome.action == "sent", (profile, outcome.reason)
    project = decide(
        make_ctx(config=merge_config("project")),
        judge=lambda _ctx: {"should_reply": True, "text": "接一句"},
    )
    assert project.action == "dropped"
