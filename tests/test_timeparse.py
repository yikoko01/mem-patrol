"""parse_ts: the production table mixes ms / seconds / ISO text in one column."""
from __future__ import annotations

import datetime

import pytest

from memorix.policy.timeparse import parse_ts


def test_none_is_zero():
    assert parse_ts(None) == 0


def test_missing_like_values():
    assert parse_ts(0) == 0
    assert parse_ts(-5) == -5


def test_epoch_seconds():
    assert parse_ts(1_792_353_646) == 1_792_353_646


def test_epoch_millis_are_normalised():
    assert parse_ts(1_792_353_646_789) == 1_792_353_646


def test_float_seconds_are_truncated():
    assert parse_ts(1_792_353_646.9) == 1_792_353_646


def test_numeric_string_is_parsed():
    assert parse_ts("1792353646") == 1_792_353_646


def test_iso_naive_string():
    raw = "2026-10-19T16:00:00"
    assert parse_ts(raw) == int(datetime.datetime.fromisoformat(raw).timestamp())


def test_iso_with_z_suffix():
    raw = "2026-10-19T16:00:00Z"
    expected = int(datetime.datetime.fromisoformat(raw.replace("Z", "")).timestamp())
    assert parse_ts(raw) == expected


def test_iso_with_offset():
    raw = "2026-10-19T16:00:00+08:00"
    assert parse_ts(raw) == int(datetime.datetime.fromisoformat(raw).timestamp())


@pytest.mark.parametrize("bad", ["not-a-date", "", " ", "2026-13-40T00:00:00"])
def test_unparseable_returns_zero(bad):
    assert parse_ts(bad) == 0


def test_millisecond_threshold_boundary():
    # 1e11 itself is not "milliseconds"; 1e11 + 1 is.
    assert parse_ts(10**11) == 10**11
    assert parse_ts(10**11 + 1) == 10**8
