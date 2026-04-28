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


# Default-stub the news fetcher so existing format_report_embed tests
# don't try to hit Cloud SQL. Individual tests override this fixture
# when they specifically want to assert news-block rendering.
@pytest.fixture(autouse=True)
def _stub_news_fetch(monkeypatch):
    monkeypatch.setattr(
        push, "fetch_top_news_articles", lambda *_a, **_kw: []
    )


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


# ── Regime-aware rendering (PR α) ─────────────────────────────────────────


def test_fmt_targets_field_orb_only_suppresses_numbers():
    """orb_only regime: don't show entry/stop/targets; emit ORB-wait callout."""
    out = push._fmt_targets_field(
        {"low": 305.83, "high": 317.05},  # placeholder values from _orb_only_plan
        294.61,
        [],
        regime="orb_only",
    )
    assert "ORB-only" in out
    assert "wait" in out.lower() or "15-min" in out
    # The placeholder numbers should NOT appear — they're not real triggers
    assert "305.83" not in out
    assert "317.05" not in out
    assert "294.61" not in out


def test_fmt_targets_field_extended_prepends_warning():
    """extended regime: keep entry/stop/targets but add a leading warning."""
    out = push._fmt_targets_field(
        {"low": 180.0, "high": 182.0},
        175.0,
        [185.0, 190.0, 195.0],
        regime="extended",
    )
    assert "Extended gap" in out
    assert "ORB" in out
    # Entry/stop/targets still rendered
    assert "180.00" in out and "182.00" in out
    assert "175.00" in out
    assert "185.00" in out


def test_fmt_targets_field_normal_regime_unchanged():
    """normal regime: identical output to the legacy no-regime call."""
    out_normal = push._fmt_targets_field(
        {"low": 275.0, "high": 276.65}, 282.71,
        [269.59, 263.53, 257.47],
        regime="normal",
    )
    out_legacy = push._fmt_targets_field(
        {"low": 275.0, "high": 276.65}, 282.71,
        [269.59, 263.53, 257.47],
    )
    assert out_normal == out_legacy
    # No regime warnings
    assert "Extended" not in out_normal
    assert "ORB-only" not in out_normal


def test_fmt_targets_field_default_is_normal():
    """Backwards-compat: callers that don't pass regime get normal rendering."""
    out = push._fmt_targets_field(
        {"low": 100.0, "high": 102.0}, 95.0, [105.0],
    )
    assert "100.00" in out
    assert "Extended" not in out
    assert "ORB-only" not in out


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


def test_embed_orb_only_regime_renders_callout():
    """orb_only regime → trade-plan field shows ORB-wait copy + tagged title."""
    row = _sample_row()
    row["report"]["regime"] = "orb_only"
    embed = push.format_report_embed(row)
    field_names = [f["name"] for f in embed["fields"]]
    assert any("ORB-only" in n for n in field_names), field_names
    plan_field = next(f for f in embed["fields"] if "ORB-only" in f["name"])
    assert "ORB-only" in plan_field["value"]
    # Placeholder entry/stop numbers should be hidden on ORB-only
    assert "275.00" not in plan_field["value"]


def test_embed_extended_regime_prepends_warning_and_tags_field():
    row = _sample_row()
    row["report"]["regime"] = "extended"
    embed = push.format_report_embed(row)
    field_names = [f["name"] for f in embed["fields"]]
    assert any("extended" in n.lower() for n in field_names), field_names
    plan_field = next(f for f in embed["fields"] if "extended" in f["name"].lower())
    assert "Extended gap" in plan_field["value"]
    # Numbers still present on extended
    assert "275.00" in plan_field["value"]


def test_embed_normal_regime_renders_legacy_field_name():
    row = _sample_row()
    row["report"]["regime"] = "normal"
    embed = push.format_report_embed(row)
    field_names = [f["name"] for f in embed["fields"]]
    assert "📐 Trade plan" in field_names
    assert not any("ORB-only" in n for n in field_names)
    assert not any("extended" in n.lower() for n in field_names)


def test_embed_missing_regime_defaults_to_normal():
    """Reports persisted before the regime field existed render as normal."""
    row = _sample_row()
    # explicitly drop regime to simulate pre-PR-α reports
    row["report"].pop("regime", None)
    embed = push.format_report_embed(row)
    field_names = [f["name"] for f in embed["fields"]]
    assert "📐 Trade plan" in field_names


# ---------------------------------------------------------------------------
# split_into_messages — one message per ticker
# ---------------------------------------------------------------------------


def test_split_no_rows_returns_one_empty_payload():
    target = date(2026, 4, 27)
    msgs = push.split_into_messages([], target)
    assert len(msgs) == 1
    assert "no reports" in msgs[0]["content"]
    assert msgs[0]["embeds"] == []


def test_split_one_row_one_message():
    msgs = push.split_into_messages([_sample_row()], date(2026, 4, 27))
    assert len(msgs) == 1
    assert len(msgs[0]["embeds"]) == 1


def test_split_emits_one_message_per_ticker():
    """Six tickers → six messages. Each one has exactly one embed."""
    rows = [_sample_row() for _ in range(6)]
    for i, r in enumerate(rows):
        r["ticker"] = f"T{i:02d}"
        r["report"]["ticker"] = f"T{i:02d}"
    msgs = push.split_into_messages(rows, date(2026, 4, 27))
    assert len(msgs) == 6
    for m in msgs:
        assert len(m["embeds"]) == 1


def test_split_header_carries_ticker_and_date():
    rows = [_sample_row()]
    rows[0]["ticker"] = "AVGO"
    rows[0]["report"]["ticker"] = "AVGO"
    msgs = push.split_into_messages(rows, date(2026, 4, 27))
    assert len(msgs) == 1
    assert "AVGO" in msgs[0]["content"]
    assert "2026-04-27" in msgs[0]["content"]


def test_split_each_message_under_size_limit():
    """One ticker per message → each well under the 6000-char envelope."""
    rows = [_sample_row() for _ in range(8)]
    for i, r in enumerate(rows):
        r["ticker"] = f"T{i:02d}"
        r["report"]["ticker"] = f"T{i:02d}"
    msgs = push.split_into_messages(rows, date(2026, 4, 27))
    for m in msgs:
        size = sum(len(json.dumps(e)) for e in m["embeds"])
        assert size <= push.MAX_EMBED_CHARS, f"size {size} > {push.MAX_EMBED_CHARS}"


def test_split_preserves_all_rows():
    """Critical: total embeds across messages == row count, no drops."""
    rows = [_sample_row() for _ in range(8)]
    for i, r in enumerate(rows):
        r["ticker"] = f"T{i:02d}"
        r["report"]["ticker"] = f"T{i:02d}"
    msgs = push.split_into_messages(rows, date(2026, 4, 27))
    total = sum(len(m["embeds"]) for m in msgs)
    assert total == len(rows)


def test_split_preserves_row_order():
    """Tickers come out in the same order they came in (DB sorts them)."""
    rows = [_sample_row() for _ in range(3)]
    for i, tk in enumerate(["AAPL", "IWM", "ZS"]):
        rows[i]["ticker"] = tk
        rows[i]["report"]["ticker"] = tk
    msgs = push.split_into_messages(rows, date(2026, 4, 27))
    extracted = [m["embeds"][0]["title"] for m in msgs]
    # Title format: "🟢/🔴/⚪ TICKER · DIRECTION · ..."
    assert "AAPL" in extracted[0]
    assert "IWM" in extracted[1]
    assert "ZS" in extracted[2]


def test_format_message_back_compat_returns_first_per_ticker():
    """format_message returns the first per-ticker payload."""
    rows = [_sample_row() for _ in range(3)]
    for i, r in enumerate(rows):
        r["ticker"] = f"T{i:02d}"
        r["report"]["ticker"] = f"T{i:02d}"
    legacy = push.format_message(rows, date(2026, 4, 27))
    new = push.split_into_messages(rows, date(2026, 4, 27))
    assert legacy == new[0]


def test_format_message_includes_date_in_header():
    msg = push.format_message([_sample_row()], date(2026, 4, 27))
    assert "2026-04-27" in msg["content"]


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


# ---------------------------------------------------------------------------
# News field formatting & integration
# ---------------------------------------------------------------------------


def _sample_articles(n: int = 3) -> list[dict]:
    """Three plausible AVGO-style headlines, deliberately varied so a
    single substring assertion proves the right one made it into the
    field (not just that *something* rendered)."""
    return [
        {
            "title": "Broadcom and Google Deal Headlines Stir Market Interest",
            "sentiment_score": 0.47,
            "relevance_score": 0.98,
            "source": "Investing.com",
            "published_ts": datetime(2026, 4, 7, 14, 12, tzinfo=timezone.utc),
        },
        {
            "title": "Nvidia Stock Drops as Iran War Heats Up. Here's the Level to Watch.",
            "sentiment_score": -0.14,
            "relevance_score": 0.63,
            "source": "Barron's",
            "published_ts": datetime(2026, 4, 7, 15, 8, tzinfo=timezone.utc),
        },
        {
            "title": "Spire Inc stock hits all-time high at 94.46 USD",
            "sentiment_score": 0.13,
            "relevance_score": 0.61,
            "source": "Investing.com",
            "published_ts": datetime(2026, 4, 7, 15, 39, tzinfo=timezone.utc),
        },
    ][:n]


def test_sentiment_label_buckets():
    assert push._sentiment_label(None) == "n/a"
    assert push._sentiment_label(0.50) == "Bullish"
    assert push._sentiment_label(0.20) == "Somewhat-Bullish"
    assert push._sentiment_label(0.00) == "Neutral"
    assert push._sentiment_label(-0.20) == "Somewhat-Bearish"
    assert push._sentiment_label(-0.50) == "Bearish"


def test_fmt_news_field_leads_with_titles():
    out = push._fmt_news_field(_sample_articles(2))
    # Header carries the aggregate read.
    assert "Mean sentiment" in out
    # Each title is rendered, and the FIRST headline is fully present
    # (proves the title is the lead, not the source).
    assert "Broadcom and Google Deal Headlines Stir Market Interest" in out
    # Source appears as a small annotation under the title.
    assert "Investing.com" in out
    assert "+0.47" in out


def test_fmt_news_field_truncates_long_title():
    long_title = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4
    article = {
        "title": long_title.strip(),
        "sentiment_score": 0.1,
        "relevance_score": 0.9,
        "source": "Wire",
    }
    out = push._fmt_news_field([article])
    # Truncated to <=90 chars + ellipsis (the formatter's per-line cap).
    # Find the title line and verify length.
    headline_line = next(line for line in out.splitlines() if line.startswith("• "))
    visible_title = headline_line.replace("• ", "").replace("**", "")
    assert len(visible_title) <= 91, f"got {len(visible_title)}: {visible_title!r}"
    assert visible_title.endswith("…")


def test_fmt_news_field_caps_at_top_n():
    # Build NEWS_TOP_N + 2 articles; only NEWS_TOP_N should render.
    articles = [
        {
            "title": f"Story number {i}",
            "sentiment_score": 0.1,
            "relevance_score": 0.5,
            "source": "Wire",
        }
        for i in range(push.NEWS_TOP_N + 2)
    ]
    out = push._fmt_news_field(articles)
    rendered = sum(1 for line in out.splitlines() if line.startswith("• "))
    assert rendered == push.NEWS_TOP_N
    # The (NEWS_TOP_N + 1)-th story isn't there.
    assert f"Story number {push.NEWS_TOP_N}" not in out


def test_fmt_news_field_no_articles_returns_failure_placeholder():
    out = push._fmt_news_field([])
    assert "unavailable" in out.lower()


def test_fmt_news_field_failed_sentiment_overrides_articles():
    # Even with articles in hand, an explicit failed_sections entry
    # for sentiment means the analyst couldn't use them — surface
    # that to the trader rather than pretending the field is healthy.
    out = push._fmt_news_field(
        _sample_articles(2),
        failed_sections=["sentiment"],
    )
    assert "sentiment unavailable" in out.lower()


def test_fmt_news_field_handles_missing_sentiment_score_gracefully():
    article = {
        "title": "Headline with no sentiment",
        "sentiment_score": None,
        "relevance_score": 0.9,
        "source": "Wire",
    }
    out = push._fmt_news_field([article])
    assert "Headline with no sentiment" in out
    # Should not crash on n/a sentiment.
    assert "n/a" in out or "—" in out


def test_format_report_embed_includes_news_field(monkeypatch):
    monkeypatch.setattr(
        push, "fetch_top_news_articles", lambda *_a, **_kw: _sample_articles(2)
    )
    embed = push.format_report_embed(_sample_row())
    field_names = [f["name"] for f in embed["fields"]]
    assert any("News" in n for n in field_names), f"expected News field, got {field_names}"
    news_value = next(f["value"] for f in embed["fields"] if "News" in f["name"])
    assert "Broadcom and Google" in news_value


def test_format_report_embed_news_field_renders_failure_when_section_failed(monkeypatch):
    # When the LLM bundle says sentiment failed, the field should
    # surface the failure even if late-arriving rows are now present.
    monkeypatch.setattr(
        push, "fetch_top_news_articles", lambda *_a, **_kw: _sample_articles(1)
    )
    embed = push.format_report_embed(_sample_row(failed=["sentiment"]))
    news_value = next(f["value"] for f in embed["fields"] if "News" in f["name"])
    assert "unavailable" in news_value.lower()
