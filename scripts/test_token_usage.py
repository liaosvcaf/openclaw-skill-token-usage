#!/usr/bin/env python3
"""Regression tests for token-usage analysis script.

Uses mock JSONL data to verify parsing, channel detection, aggregation,
and formatting logic. Run with: python3 -m pytest test_token_usage.py -v
"""

import json
import pytest
from datetime import datetime, timezone

from token_usage import (
    detect_channel,
    extract_user_text,
    parse_session_lines,
    aggregate,
    fmt_tokens,
    fmt_cost,
    to_local,
)


# ── Helpers ──

def make_user_msg(text, ts="2026-02-02T20:00:00Z"):
    """Build a JSONL line for a user message."""
    return json.dumps({
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    })


def make_assistant_msg(
    model="claude-opus-4-5",
    provider="anthropic",
    ts="2026-02-02T20:00:01Z",
    input_tok=10,
    output_tok=50,
    cache_read=1000,
    cache_write=500,
    cost_input=0.00005,
    cost_output=0.00125,
    cost_cache_read=0.0005,
    cost_cache_write=0.003125,
):
    """Build a JSONL line for an assistant message with usage."""
    total = input_tok + output_tok + cache_read + cache_write
    cost_total = cost_input + cost_output + cost_cache_read + cost_cache_write
    return json.dumps({
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "model": model,
            "provider": provider,
            "content": [{"type": "text", "text": "Response text."}],
            "usage": {
                "input": input_tok,
                "output": output_tok,
                "cacheRead": cache_read,
                "cacheWrite": cache_write,
                "totalTokens": total,
                "cost": {
                    "input": cost_input,
                    "output": cost_output,
                    "cacheRead": cost_cache_read,
                    "cacheWrite": cost_cache_write,
                    "total": cost_total,
                },
            },
        },
    })


# ── detect_channel ──

class TestDetectChannel:
    def test_telegram(self):
        assert detect_channel("[Telegram Chunhua Liao id:123]") == "telegram"

    def test_discord(self):
        assert detect_channel("[Discord #general user:Alice]") == "discord"

    def test_signal(self):
        assert detect_channel("[Signal conversation with Bob]") == "signal"

    def test_slack(self):
        assert detect_channel("[Slack #random]") == "slack"

    def test_webchat(self):
        assert detect_channel("hello\n[message_id: abc-123]") == "webchat"

    def test_other(self):
        assert detect_channel("just a plain message") == "other"

    def test_empty(self):
        assert detect_channel("") == "other"

    def test_telegram_takes_precedence_over_message_id(self):
        """Telegram messages also contain [message_id:] but should be detected as telegram."""
        text = "[Telegram Chunhua Liao id:123]\n[message_id: xyz]"
        assert detect_channel(text) == "telegram"


# ── extract_user_text ──

class TestExtractUserText:
    def test_list_content(self):
        msg = {"content": [{"type": "text", "text": "hello world"}]}
        assert extract_user_text(msg) == "hello world"

    def test_string_content(self):
        msg = {"content": "hello string"}
        assert extract_user_text(msg) == "hello string"

    def test_empty_content(self):
        msg = {"content": []}
        assert extract_user_text(msg) == ""

    def test_no_content(self):
        msg = {}
        assert extract_user_text(msg) == ""

    def test_multiple_blocks_takes_first_text(self):
        msg = {"content": [
            {"type": "image", "url": "..."},
            {"type": "text", "text": "caption here"},
        ]}
        assert extract_user_text(msg) == "caption here"


# ── Channel attribution regression (the bug that showed 96% Telegram) ──

class TestChannelAttribution:
    """Regression: channel must be per-message, not sticky per-session."""

    def test_channel_resets_between_messages(self):
        """After a Telegram user msg, a webchat user msg must reset channel to webchat."""
        lines = [
            make_user_msg("[Telegram user id:1] hello", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(ts="2026-02-02T20:00:01Z"),
            make_user_msg("webchat follow-up\n[message_id: abc]", ts="2026-02-02T20:01:00Z"),
            make_assistant_msg(ts="2026-02-02T20:01:01Z"),
        ]
        entries = parse_session_lines(lines, "test-sess")
        assert len(entries) == 2
        assert entries[0]["channel"] == "telegram"
        assert entries[1]["channel"] == "webchat"

    def test_channel_not_sticky_across_three_switches(self):
        """Channel must track correctly across telegram -> webchat -> telegram."""
        lines = [
            make_user_msg("[Telegram user] msg1", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(ts="2026-02-02T20:00:01Z"),
            make_user_msg("msg2\n[message_id: m2]", ts="2026-02-02T20:01:00Z"),
            make_assistant_msg(ts="2026-02-02T20:01:01Z"),
            make_user_msg("[Telegram user] msg3", ts="2026-02-02T20:02:00Z"),
            make_assistant_msg(ts="2026-02-02T20:02:01Z"),
        ]
        entries = parse_session_lines(lines, "test-sess")
        channels = [e["channel"] for e in entries]
        assert channels == ["telegram", "webchat", "telegram"]

    def test_plain_message_resets_to_other(self):
        """A user message with no channel markers should be 'other', not inherit previous."""
        lines = [
            make_user_msg("[Telegram user] hello", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(ts="2026-02-02T20:00:01Z"),
            make_user_msg("system restart notification", ts="2026-02-02T20:01:00Z"),
            make_assistant_msg(ts="2026-02-02T20:01:01Z"),
        ]
        entries = parse_session_lines(lines, "test-sess")
        assert entries[0]["channel"] == "telegram"
        assert entries[1]["channel"] == "other"

    def test_multiple_assistant_calls_per_user_turn(self):
        """Multiple assistant responses after one user msg all get the same channel."""
        lines = [
            make_user_msg("[Telegram user] do something", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(ts="2026-02-02T20:00:01Z"),
            make_assistant_msg(ts="2026-02-02T20:00:02Z"),
            make_assistant_msg(ts="2026-02-02T20:00:03Z"),
        ]
        entries = parse_session_lines(lines, "test-sess")
        assert len(entries) == 3
        assert all(e["channel"] == "telegram" for e in entries)


# ── parse_session_lines ──

class TestParseSessionLines:
    def test_empty_input(self):
        assert parse_session_lines([], "sess") == []

    def test_malformed_json_skipped(self):
        lines = [
            "not json at all",
            make_user_msg("hello\n[message_id: m1]"),
            "{broken json",
            make_assistant_msg(),
        ]
        entries = parse_session_lines(lines, "sess1234")
        assert len(entries) == 1
        assert entries[0]["channel"] == "webchat"

    def test_session_id_truncated(self):
        lines = [
            make_user_msg("hi\n[message_id: m1]"),
            make_assistant_msg(),
        ]
        entries = parse_session_lines(lines, "abcdefghijklmnop")
        assert entries[0]["session_id"] == "abcdefgh"

    def test_assistant_without_usage_skipped(self):
        line = json.dumps({
            "timestamp": "2026-02-02T20:00:01Z",
            "message": {
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "no usage"}],
            },
        })
        lines = [make_user_msg("hi\n[message_id: m1]"), line]
        entries = parse_session_lines(lines, "sess")
        assert len(entries) == 0

    def test_assistant_without_timestamp_skipped(self):
        line = json.dumps({
            "message": {
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "no ts"}],
                "usage": {"input": 1, "output": 1, "totalTokens": 2,
                           "cost": {"total": 0.01}},
            },
        })
        lines = [make_user_msg("hi\n[message_id: m1]"), line]
        entries = parse_session_lines(lines, "sess")
        assert len(entries) == 0

    def test_usage_fields_extracted(self):
        lines = [
            make_user_msg("hi\n[message_id: m1]"),
            make_assistant_msg(
                input_tok=100, output_tok=200,
                cache_read=3000, cache_write=1500,
                cost_input=0.0005, cost_output=0.005,
                cost_cache_read=0.0015, cost_cache_write=0.009375,
            ),
        ]
        entries = parse_session_lines(lines, "sess")
        e = entries[0]
        assert e["input"] == 100
        assert e["output"] == 200
        assert e["cache_read"] == 3000
        assert e["cache_write"] == 1500
        assert e["total"] == 4800
        assert abs(e["cost"] - 0.016375) < 1e-9
        assert abs(e["cost_input"] - 0.0005) < 1e-9
        assert abs(e["cost_output"] - 0.005) < 1e-9

    def test_model_and_provider(self):
        lines = [
            make_user_msg("hi\n[message_id: m1]"),
            make_assistant_msg(model="gemini-flash", provider="openrouter"),
        ]
        entries = parse_session_lines(lines, "sess")
        assert entries[0]["model"] == "gemini-flash"
        assert entries[0]["provider"] == "openrouter"

    def test_date_and_hour_localized(self):
        """Timestamp 2026-02-03T04:30:00Z = 2026-02-02 20:30 PST."""
        lines = [
            make_user_msg("hi\n[message_id: m1]", ts="2026-02-03T04:30:00Z"),
            make_assistant_msg(ts="2026-02-03T04:30:01Z"),
        ]
        entries = parse_session_lines(lines, "sess")
        assert entries[0]["date"] == "2026-02-02"
        assert entries[0]["hour"] == 20

    def test_no_user_msg_before_assistant_gives_unknown_channel(self):
        """If assistant responds before any user message, channel is 'unknown'."""
        lines = [make_assistant_msg()]
        entries = parse_session_lines(lines, "sess")
        assert len(entries) == 1
        assert entries[0]["channel"] == "unknown"


# ── aggregate ──

class TestAggregate:
    def _make_entries(self):
        lines = [
            make_user_msg("[Telegram user] msg1", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(
                model="opus", input_tok=10, output_tok=50,
                cache_read=1000, cache_write=500,
                cost_input=0.00005, cost_output=0.00125,
                cost_cache_read=0.0005, cost_cache_write=0.003125,
                ts="2026-02-02T20:00:01Z",
            ),
            make_user_msg("webchat msg\n[message_id: m2]", ts="2026-02-02T21:00:00Z"),
            make_assistant_msg(
                model="flash", input_tok=5, output_tok=30,
                cache_read=500, cache_write=200,
                cost_input=0.000002, cost_output=0.000075,
                cost_cache_read=0.00002, cost_cache_write=0.0000825,
                ts="2026-02-02T21:00:01Z",
            ),
        ]
        return parse_session_lines(lines, "agg-test")

    def test_totals(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        t = agg["totals"]
        assert t["calls"] == 2
        assert t["input"] == 15
        assert t["output"] == 80
        assert t["cache_read"] == 1500
        assert t["cache_write"] == 700

    def test_by_channel(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        assert "telegram" in agg["by_channel"]
        assert "webchat" in agg["by_channel"]
        assert agg["by_channel"]["telegram"]["calls"] == 1
        assert agg["by_channel"]["webchat"]["calls"] == 1

    def test_by_model(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        assert "opus" in agg["by_model"]
        assert "flash" in agg["by_model"]
        assert agg["by_model"]["opus"]["output"] == 50
        assert agg["by_model"]["flash"]["output"] == 30

    def test_by_model_cost_rates(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        opus = agg["by_model"]["opus"]
        # Verify $/M rates can be computed correctly
        in_rate = opus["cost_input"] / opus["input"] * 1_000_000
        out_rate = opus["cost_output"] / opus["output"] * 1_000_000
        assert abs(in_rate - 5.0) < 0.01
        assert abs(out_rate - 25.0) < 0.01

    def test_by_date(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        # Both entries are on 2026-02-02 (PST)
        assert len(agg["by_date"]) == 1
        assert "2026-02-02" in agg["by_date"]
        assert agg["by_date"]["2026-02-02"]["calls"] == 2

    def test_by_hour(self):
        entries = self._make_entries()
        agg = aggregate(entries)
        assert agg["by_hour"][12]["calls"] == 1  # 20:00 UTC = 12:00 PST
        assert agg["by_hour"][13]["calls"] == 1  # 21:00 UTC = 13:00 PST

    def test_empty_entries(self):
        agg = aggregate([])
        assert agg["totals"]["calls"] == 0
        assert len(agg["by_date"]) == 0


# ── Formatting helpers ──

class TestFormatting:
    def test_fmt_tokens_millions(self):
        assert fmt_tokens(1_500_000) == "1.5M"

    def test_fmt_tokens_thousands(self):
        assert fmt_tokens(42_000) == "42.0K"

    def test_fmt_tokens_small(self):
        assert fmt_tokens(999) == "999"

    def test_fmt_tokens_zero(self):
        assert fmt_tokens(0) == "0"

    def test_fmt_cost_dollars(self):
        assert fmt_cost(12.345) == "$12.35"

    def test_fmt_cost_cents(self):
        assert fmt_cost(0.0567) == "$0.057"

    def test_fmt_cost_tiny(self):
        assert fmt_cost(0.00123) == "$0.0012"

    def test_fmt_cost_zero(self):
        assert fmt_cost(0) == "$0.0000"


# ── to_local ──

class TestToLocal:
    def test_z_suffix(self):
        dt = to_local("2026-02-02T08:00:00Z")
        assert dt.hour == 0  # UTC 08:00 - 8h = 00:00 PST

    def test_iso_offset(self):
        dt = to_local("2026-02-02T08:00:00+00:00")
        assert dt.hour == 0

    def test_invalid_returns_none(self):
        assert to_local("not a date") is None

    def test_empty_returns_none(self):
        assert to_local("") is None


# ── End-to-end JSON output ──

class TestJsonOutput:
    def test_json_round_trip(self):
        """Verify aggregate output is JSON-serializable with correct structure."""
        lines = [
            make_user_msg("[Telegram user] hi", ts="2026-02-02T20:00:00Z"),
            make_assistant_msg(ts="2026-02-02T20:00:01Z"),
        ]
        entries = parse_session_lines(lines, "json-test")
        agg = aggregate(entries)

        # Simulate report_json
        out = {
            "totals": agg["totals"],
            "by_date": {k: dict(v) for k, v in agg["by_date"].items()},
            "by_model": {k: dict(v) for k, v in agg["by_model"].items()},
            "by_channel": {k: dict(v) for k, v in agg["by_channel"].items()},
            "by_session": {k: dict(v) for k, v in agg["by_session"].items()},
            "by_hour": {str(k): dict(v) for k, v in agg["by_hour"].items()},
        }
        serialized = json.dumps(out)
        parsed = json.loads(serialized)
        assert parsed["totals"]["calls"] == 1
        assert "telegram" in parsed["by_channel"]
