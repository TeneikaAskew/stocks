"""Unit tests for gcp.insight_discord_push.

Covers embed formatting (truncation, field layout, colour mapping),
the payload-builder cap on embed count, the date resolution helper,
and the no-rows / no-webhook fall-throughs in main().
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from gcp import insight_discord_push as push


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


def test_truncate_under_limit_unchanged():
    assert push._truncate("short string", 100) == "short string"


def test_truncate_over_limit_appends_ellipsis():
    out = push._truncate("a" * 50, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_truncate_handles_none():
    assert push._truncate(None, 10) == ""


def test_truncate_handles_empty_string():
    assert push._truncate("", 10) == ""


# ---------------------------------------------------------------------------
# Field formatters
# ---------------------------------------------------------------------------


def test_fmt_levels_field_renders_dict():
    out = push._fmt_levels_field({"EMA 20": 256.36, "SMA 200": 244.59})
    assert "EMA 20" in out and "256.36" in out
    assert "SMA 200" in out and "244.59" in out


def test_fmt_levels_field_skips_none_values():
    out = push._fmt_levels_field({"EMA": None, "SMA": 100.0})
    assert "EMA" not in out
    assert "SMA" in out


def test_fmt_levels_field_empty_dict_returns_dash():
    assert push._fmt_levels_field({}) == "—"


def test_fmt_levels_field_string_value_passed_through():
    out = push._fmt_levels_field({"label": "string-value"})
    assert "string-value" in out


def test_fmt_targets_field_full_plan():
    out = push._fmt_targets_field(
        {"low": 275.0, "high": 276.65},
        282.71,
        [269.59, 263.53, 257.47],
    )
    assert "275.00" in out and "276.65" in out
    assert "282.71" in out
    assert "269.59" in out and "257.47" in out


def test_fmt_targets_field_handles_missing_pieces():
    out = push._fmt_targets_field(None, None, None)
    assert out == "—"


def test_fmt_targets_field_truncates_to_three_targets():
    out = push._fmt_targets_field(None, None, [1, 2, 3, 4, 5])
    assert "4.00" not in out
    assert "5.00" not in out


def test_fmt_risk_flags_field_renders_severity_marker():
    out = push._fmt_risk_flags_field([
        {"severity": "warn", "persona": "neutral", "message": "Stop too tight"},
        {"severity": "info", "persona": "aggressive", "message": "Targets close"},
    ])
    assert "⚠️" in out
    assert "ℹ️" in out
    assert "Stop too tight" in out
    assert "Targets close" in out


def test_fmt_risk_flags_field_empty_returns_dash():
    assert push._fmt_risk_flags_field([]) == "—"


def test_fmt_catalysts_field_marks_high_impact():
    out = push._fmt_catalysts_field([
        {"date": "2026-04-30", "name": "GDP", "impact": "high"},
        {"date": "2026-04-29", "name": "Construction", "impact": "medium"},
    ])
    assert "🔴" in out  # high-impact marker
    assert "🟡" in out  # medium-impact marker
    assert "GDP" in out


def test_fmt_catalysts_field_caps_at_eight():
    long_list = [
        {"date": f"2026-04-{15 + i}", "name": f"Event {i}", "impact": "medium"}
        for i in range(15)
    ]
    out = push._fmt_catalysts_field(long_list)
    # First 8 should appear, 9th onward shouldn't
    assert "Event 0" in out
    assert "Event 7" in out
    assert "Event 8" not in out


# ---------------------------------------------------------------------------
# format_report_embed
# ---------------------------------------------------------------------------


def _sample_row(direction: str = "short", failed: list | None = None) -> dict:
    return {
        "ticker": "IWM",
        "as_of": datetime(2026, 4, 27, 12, 45, 52, tzinfo=timezone.utc),
        "cost_usd": 0.0031,
        "latency_ms": 14253,
        "report": {
            "ticker": "IWM",
            "direction": direction,
            "conviction": "high",
            "confidence_score": 0.7,
            "thesis": "IWM faces strong headwinds.",
            "entry_zone": {"low": 275.0, "high": 276.65},
            "stop": 282.71,
            "targets": [269.59, 263.53, 257.47],
            "invalidation": "Break above 282.71",
            "key_levels": {"EMA 20": 256.36, "SMA 200": 244.59},
            "strat_status": {
                "last_candle": "1",
                "ftfc_score": 0.0,
                "ftfc_direction": "mixed",
                "in_force_combo": None,
            },
            "risk_flags": [
                {"severity": "warn", "persona": "neutral", "message": "Stop tight"},
            ],
            "catalysts": [
                {"date": "2026-04-30", "name": "GDP", "impact": "high"},
            ],
            "failed_sections": failed or [],
        },
    }


def test_embed_long_direction_uses_green():
    embed = push.format_report_embed(_sample_row(direction="long"))
    assert embed["color"] == push.DIRECTION_COLOURS["long"]
    assert "🟢" in embed["title"]


def test_embed_short_direction_uses_red():
    embed = push.format_report_embed(_sample_row(direction="short"))
    assert embed["color"] == push.DIRECTION_COLOURS["short"]
    assert "🔴" in embed["title"]


def test_embed_unknown_direction_uses_default_colour():
    embed = push.format_report_embed(_sample_row(direction=""))
    assert embed["color"] == push.DEFAULT_COLOUR
    assert "⚪" in embed["title"]


def test_embed_includes_ticker_and_conviction():
    embed = push.format_report_embed(_sample_row())
    assert "IWM" in embed["title"]
    assert "SHORT" in embed["title"]
    assert "high" in embed["title"]


def test_embed_thesis_in_description():
    embed = push.format_report_embed(_sample_row())
    assert "headwinds" in embed["description"]


def test_embed_failed_sections_surface_in_description():
    embed = push.format_report_embed(_sample_row(failed=["sentiment"]))
    assert "sentiment" in embed["description"]
    assert "failed sections" in embed["description"]


def test_embed_has_expected_fields():
    embed = push.format_report_embed(_sample_row())
    field_names = [f["name"] for f in embed["fields"]]
    assert "📐 Trade plan" in field_names
    assert "🎲 Strat / FTFC" in field_names
    assert "📍 Key levels" in field_names
    assert "⚠️ Risk flags" in field_names
    assert "📅 Catalysts" in field_names
    assert "🛑 Invalidation" in field_names


def test_embed_footer_includes_metadata():
    embed = push.format_report_embed(_sample_row())
    footer = embed.get("footer", {}).get("text", "")
    assert "0.70" in footer  # confidence
    assert "0.0031" in footer  # cost
    assert "14253" in footer  # latency


def test_embed_omits_invalidation_field_when_missing():
    row = _sample_row()
    row["report"]["invalidation"] = None
    embed = push.format_report_embed(row)
    field_names = [f["name"] for f in embed["fields"]]
    assert "🛑 Invalidation" not in field_names


# ---------------------------------------------------------------------------
# format_message
# ---------------------------------------------------------------------------


def test_format_message_no_rows_includes_header_only():
    target = date(2026, 4, 27)
    msg = push.format_message([], target)
    assert "no reports" in msg["content"]
    assert msg["embeds"] == []


def test_format_message_caps_embeds_at_ten():
    rows = [_sample_row() for _ in range(15)]
    # Differentiate tickers so each embed is unique
    for i, r in enumerate(rows):
        r["ticker"] = f"T{i:02d}"
        r["report"]["ticker"] = f"T{i:02d}"
    msg = push.format_message(rows, date(2026, 4, 27))
    assert len(msg["embeds"]) <= push.MAX_EMBEDS_PER_MESSAGE
    assert "showing first" in msg["content"]


def test_format_message_includes_date_in_header():
    msg = push.format_message([_sample_row()], date(2026, 4, 27))
    assert "2026-04-27" in msg["content"]


def test_format_message_envelope_under_size_limit():
    rows = [_sample_row() for _ in range(3)]
    msg = push.format_message(rows, date(2026, 4, 27))
    payload_size = len(json.dumps(msg["embeds"]))
    assert payload_size <= push.MAX_EMBED_CHARS


# ---------------------------------------------------------------------------
# _resolve_target_date
# ---------------------------------------------------------------------------


def test_resolve_target_date_default_is_utc_today(monkeypatch):
    monkeypatch.delenv("INSIGHT_PUSH_DATE", raising=False)
    out = push._resolve_target_date()
    assert out == datetime.now(timezone.utc).date()


def test_resolve_target_date_honours_env(monkeypatch):
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "2026-01-15")
    assert push._resolve_target_date() == date(2026, 1, 15)


def test_resolve_target_date_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "not-a-date")
    out = push._resolve_target_date()
    assert out == datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# main() — exit-code paths
# ---------------------------------------------------------------------------


def test_main_no_webhook_prints_payload_and_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("INSIGHT_PUSH_TICKER", raising=False)
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "2026-04-27")
    monkeypatch.setattr(push, "fetch_reports_for_date", lambda *_a, **_k: [_sample_row()])
    code = push.main()
    assert code == 0
    captured = capsys.readouterr()
    # Webhook missing → main prints the payload to stdout instead of POSTing
    assert "embeds" in captured.out


def test_main_no_rows_skips_push(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "2026-04-27")
    monkeypatch.delenv("INSIGHT_PUSH_TICKER", raising=False)
    monkeypatch.setattr(push, "fetch_reports_for_date", lambda *_a, **_k: [])

    posted = {"called": False}

    def fake_send(*_a, **_k):
        posted["called"] = True
        return 204

    monkeypatch.setattr(push, "send_to_discord", fake_send)
    code = push.main()
    assert code == 0
    assert posted["called"] is False


def test_main_happy_path_posts_and_exits_zero(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "2026-04-27")
    monkeypatch.delenv("INSIGHT_PUSH_TICKER", raising=False)
    monkeypatch.setattr(push, "fetch_reports_for_date", lambda *_a, **_k: [_sample_row()])

    captured = {}

    def fake_send(message, webhook_url, timeout=15):
        captured["message"] = message
        captured["url"] = webhook_url
        return 204

    monkeypatch.setattr(push, "send_to_discord", fake_send)
    code = push.main()
    assert code == 0
    assert captured["url"] == "https://example.com/webhook"
    assert captured["message"]["embeds"]


def test_main_send_failure_returns_one(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("INSIGHT_PUSH_DATE", "2026-04-27")
    monkeypatch.delenv("INSIGHT_PUSH_TICKER", raising=False)
    monkeypatch.setattr(push, "fetch_reports_for_date", lambda *_a, **_k: [_sample_row()])

    def fake_send(*_a, **_k):
        raise RuntimeError("Discord 500")

    monkeypatch.setattr(push, "send_to_discord", fake_send)
    code = push.main()
    assert code == 1
