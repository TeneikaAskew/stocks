"""Unit tests for lib.agents.summarizers.

All tests monkey-patch `lib.agents.summarizers._query` with a fake
that returns canned DataFrames, so nothing depends on a live DB.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from lib.agents import summarizers
from lib.agents.schema import JournalRef


@pytest.fixture
def patch_query(monkeypatch):
    """Install a fake _query that returns canned results per SQL substring."""
    store: dict[str, pd.DataFrame] = {}

    def set_result(needle: str, df: pd.DataFrame) -> None:
        store[needle] = df

    def fake_query(sql: str, params=None):
        for needle, df in store.items():
            if needle in sql:
                return df
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    return set_result


# ---------------------------------------------------------------------------
# summarize_market_context
# ---------------------------------------------------------------------------


def test_market_context_trending_up(patch_query):
    patch_query(
        "market_data_daily",
        pd.DataFrame([{
            "date": date(2026, 4, 15),
            "open": 500.0, "high": 505.0, "low": 499.0, "close": 504.0,
            "volume": 75_000_000, "sma_200": 480.0, "ema_20": 500.0,
            "ema_50": 495.0, "rsi_14": 62.0, "macd": 0.8, "macd_signal": 0.5,
            "macd_histogram": 0.3, "bb_upper": 510.0, "bb_lower": 490.0,
            "bb_pct": 0.75, "atr_14": 4.2, "rvol": 1.2,
            "volatility_20d": 0.15, "price_vs_ema20": 0.008,
        }]),
    )
    out = summarizers.summarize_market_context("SPY")
    assert out["available"] is True
    assert out["close"] == 504.0
    assert out["regime"] == "trending_up"
    assert out["vol_tag"] == "normal"
    assert out["above_sma_200"] is True


def test_market_context_trending_down(patch_query):
    patch_query(
        "market_data_daily",
        pd.DataFrame([{
            "date": date(2026, 4, 15),
            "close": 450.0, "sma_200": 480.0, "ema_20": 455.0,
            "ema_50": None, "rsi_14": 38.0, "macd": None, "macd_signal": None,
            "macd_histogram": None, "bb_upper": None, "bb_lower": None,
            "bb_pct": None, "atr_14": None, "rvol": None,
            "volatility_20d": 0.28, "price_vs_ema20": -0.011,
            "open": None, "high": None, "low": None, "volume": None,
        }]),
    )
    out = summarizers.summarize_market_context("SPY")
    assert out["regime"] == "trending_down"
    assert out["vol_tag"] == "elevated"
    assert out["above_sma_200"] is False


def test_market_context_unavailable_when_empty(patch_query):
    out = summarizers.summarize_market_context("SPY")  # no patched result
    assert out == {"available": False, "reason": "no market_data_daily row for SPY"}


# ---------------------------------------------------------------------------
# summarize_strat_status
# ---------------------------------------------------------------------------


def test_strat_status_extracts_trigger_levels(monkeypatch):
    """summarize_strat_status delegates to lib.strat.compute_strat_status —
    the same helper premarket_brief calls. Patch the helper directly.
    Uses the new v2 combo naming (212_bull_reversal) introduced in this PR."""
    import lib.strat as strat_mod

    def fake_compute(ticker, **kwargs):
        return {
            "available": True,
            "ticker": ticker,
            "date": "2026-04-15",
            "last_candle": "2U",
            "in_force_combo": "212_bull_reversal",
            "strat_setup": True,
            "ftfc_score": 0.6,
            "ftfc_direction": "bullish",
            "ftfc_labels": {"D": "2U", "W": "2U", "M": "1"},
            "trigger_high": 503.5,
            "trigger_low": 498.2,
        }

    monkeypatch.setattr(strat_mod, "compute_strat_status", fake_compute)
    out = summarizers.summarize_strat_status("SPY")
    assert out["available"] is True
    assert out["last_candle"] == "2U"
    assert out["in_force_combo"] == "212_bull_reversal"
    assert out["trigger_high"] == 503.5
    assert out["trigger_low"] == 498.2
    assert out["ftfc_direction"] == "bullish"


def test_strat_status_handles_unavailable(monkeypatch):
    """When the shared helper returns available=False (insufficient bars,
    null index, etc.) the summarizer surfaces an unavailable envelope."""
    import lib.strat as strat_mod

    monkeypatch.setattr(
        strat_mod, "compute_strat_status",
        lambda ticker, **kw: {"available": False, "reason": "insufficient daily bars for SPY"},
    )
    out = summarizers.summarize_strat_status("SPY")
    assert out["available"] is False
    assert "insufficient daily bars" in out["reason"]


# ---------------------------------------------------------------------------
# summarize_options_flow
# ---------------------------------------------------------------------------


def test_options_flow_ratios_and_top_oi(patch_query):
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            {"option_type": "calls", "strike": 500, "volume": 10_000,
             "open_interest": 50_000, "implied_volatility": 0.18, "delta": 0.5},
            {"option_type": "calls", "strike": 505, "volume": 5_000,
             "open_interest": 30_000, "implied_volatility": 0.20, "delta": 0.4},
            {"option_type": "puts", "strike": 495, "volume": 8_000,
             "open_interest": 40_000, "implied_volatility": 0.22, "delta": -0.45},
            {"option_type": "puts", "strike": 490, "volume": 3_000,
             "open_interest": 25_000, "implied_volatility": 0.24, "delta": -0.35},
        ]),
    )
    out = summarizers.summarize_options_flow("SPY")
    assert out["call_volume"] == 15_000
    assert out["put_volume"] == 11_000
    assert out["put_call_ratio"] == round(11_000 / 15_000, 3)
    assert 500 in out["top_oi_strikes"]
    assert out["max_pain_strike_proxy"] == 500  # highest OI strike
    assert out["vol_weighted_iv"] is not None


def test_options_flow_unavailable(patch_query):
    out = summarizers.summarize_options_flow("SPY")
    assert out["available"] is False


# ---------------------------------------------------------------------------
# summarize_signals_history
# ---------------------------------------------------------------------------


def test_signals_history_counts_and_recent(patch_query):
    patch_query(
        "signal_alerts",
        pd.DataFrame([
            {"alert_ts": "2026-04-15 14:30:00", "direction": "CALL",
             "strength_label": "strong", "total_score": 4.5},
            {"alert_ts": "2026-04-15 13:00:00", "direction": "CALL",
             "strength_label": "weak", "total_score": 2.0},
            {"alert_ts": "2026-04-14 14:30:00", "direction": "PUT",
             "strength_label": "strong", "total_score": 4.1},
        ]),
    )
    out = summarizers.summarize_signals_history("SPY")
    assert out["total_alerts"] == 3
    assert out["call_count"] == 2
    assert out["put_count"] == 1
    assert len(out["recent"]) == 3
    assert out["recent"][0]["direction"] == "CALL"


def test_signals_history_empty_is_available(patch_query):
    out = summarizers.summarize_signals_history("SPY")
    assert out["available"] is True
    assert out["total_alerts"] == 0


# ---------------------------------------------------------------------------
# summarize_backtest_metrics — replaced from a `trades`-table win-rate
# aggregator with a catalyst-analog matcher (see lib/agents/summarizers.py).
# Tests now check the new shape: pattern features, analog count, forward-
# return statistics, and top analogs.
# ---------------------------------------------------------------------------


def _synth_daily_bars(n: int = 400) -> pd.DataFrame:
    """Build a synthetic OHLCV series long enough for the analog matcher.
    Need >= 220 rows (sma_200 warm-up of 200 + 20-row tail exclusion)
    so the historical window has any rows with non-NaN
    close_vs_sma200_pct."""
    import numpy as np
    rng = np.random.default_rng(42)
    base = 100.0
    rows = []
    from datetime import date, timedelta
    d = date(2023, 1, 1)
    for i in range(n):
        # Weekday-only series
        while d.weekday() >= 5:
            d = d + timedelta(days=1)
        change = rng.normal(0.0, 0.01)
        # Plant gap-up "analogs" every 50 bars after the SMA200 warm-up
        # so the matcher always has multiple windowed candidates.
        gap_up = i >= 220 and ((i - 220) % 30 == 0)
        open_px = base * (1 + (0.04 if gap_up else change))
        close_px = open_px * (1 + rng.normal(0.0, 0.01))
        high_px = max(open_px, close_px) * (1 + abs(rng.normal(0, 0.005)))
        low_px = min(open_px, close_px) * (1 - abs(rng.normal(0, 0.005)))
        volume = int(1_000_000 * (3 if gap_up else 1) * (1 + abs(rng.normal(0, 0.1))))
        rows.append({
            "date": d, "open": open_px, "high": high_px, "low": low_px,
            "close": close_px, "volume": volume,
        })
        base = close_px
        d = d + timedelta(days=1)
    return pd.DataFrame(rows)


def test_backtest_metrics_returns_analog_pattern(patch_query):
    """Analog backtest should compute today's pattern features, find
    historical matches in the same series, and report forward returns."""
    patch_query("market_data_daily", _synth_daily_bars())
    # cross_ticker=False keeps the test focused on same-ticker matching;
    # the cross-ticker path is exercised separately in
    # test_backtest_metrics_cross_ticker_disabled.
    out = summarizers.summarize_backtest_metrics("SPY", cross_ticker=False)
    assert out["available"] is True
    # Engineered pattern features for "today" (last bar)
    pattern = out["pattern_today"]
    for k in ("gap_pct", "vol_ratio", "rsi_14", "close_vs_sma200_pct",
              "close_vs_ema20_pct"):
        assert k in pattern
    # We planted gap-up bars on a fixed cadence — the matcher should
    # always surface at least one under the progressive tolerance bands.
    assert out["analog_count"] >= 1
    assert "forward_returns" in out
    assert out["cross_ticker_used"] is False


def test_backtest_metrics_unavailable_empty(patch_query):
    """No bars in market_data_daily → analog backtest unavailable."""
    out = summarizers.summarize_backtest_metrics("SPY")
    assert out["available"] is False


def test_backtest_metrics_walks_back_past_placeholder_today(patch_query):
    """Audit 2026-05-08 G.P2.13: when the morning insight cron fires,
    the daily fetcher may have written a pre-RTH-close placeholder row
    for today with NaN volume. Old behavior: backtest fails with
    'today's row has missing indicator features'. New behavior: walk
    back to the most recent COMPLETE bar so we use yesterday's pattern
    rather than failing the section."""
    df = _synth_daily_bars()
    # Replace the last row with a placeholder (NaN close + NaN volume).
    # This is what the morning fetcher sometimes writes before RTH closes.
    df.iloc[-1, df.columns.get_loc("close")] = None
    df.iloc[-1, df.columns.get_loc("volume")] = None
    patch_query("market_data_daily", df)
    out = summarizers.summarize_backtest_metrics("SPY", cross_ticker=False)
    assert out["available"] is True, out.get("reason")
    assert out["pattern_is_proxy"] is True  # walked back to yesterday
    # The pattern date is now D-1 (the last complete bar)
    assert out["pattern_today"]["date"] != str(df.iloc[-1]["date"])


def test_backtest_metrics_no_proxy_when_today_complete(patch_query):
    """Defensive: when the latest row is complete, pattern_today comes
    from it and pattern_is_proxy is False."""
    patch_query("market_data_daily", _synth_daily_bars())
    out = summarizers.summarize_backtest_metrics("SPY", cross_ticker=False)
    assert out["available"] is True
    assert out["pattern_is_proxy"] is False


# ---------------------------------------------------------------------------
# summarize_catalysts
# ---------------------------------------------------------------------------


def test_catalysts_merges_economic_and_earnings(patch_query):
    patch_query(
        "economic_events",
        pd.DataFrame([
            {"event_date": "2026-04-16", "event_name": "CPI", "importance": "high"},
            {"event_date": "2026-04-18", "event_name": "FOMC", "importance": "high"},
        ]),
    )
    patch_query(
        "earnings_calendar",
        pd.DataFrame([
            {"earnings_date": "2026-04-17", "company_name": "SPDR S&P 500"},
        ]),
    )
    out = summarizers.summarize_catalysts("SPY", as_of=date(2026, 4, 15))
    assert out["available"] is True
    events = out["events"]
    assert len(events) == 3
    # Sorted by date
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)
    kinds = {e["kind"] for e in events}
    assert "economic" in kinds
    assert "earnings" in kinds


# ---------------------------------------------------------------------------
# retrieve_similar_journal
# ---------------------------------------------------------------------------


def test_retrieve_similar_journal_returns_refs(patch_query):
    patch_query(
        "journal_entries",
        pd.DataFrame([
            {"id": "00000000-0000-0000-0000-000000000001", "ticker": "SPY",
             "direction": "CALL", "return_pct": 2.1, "cosine_distance": 0.08},
            {"id": "00000000-0000-0000-0000-000000000002", "ticker": "SPY",
             "direction": "PUT", "return_pct": -0.5, "cosine_distance": 0.15},
        ]),
    )
    refs = summarizers.retrieve_similar_journal("SPY", [0.1] * 768, k=2)
    assert len(refs) == 2
    assert all(isinstance(r, JournalRef) for r in refs)
    assert refs[0].id.endswith("0001")
    assert refs[0].cosine_distance == 0.08


def test_retrieve_similar_journal_empty_embedding_returns_empty():
    assert summarizers.retrieve_similar_journal("SPY", []) == []


# ---------------------------------------------------------------------------
# build_context_bundle
# ---------------------------------------------------------------------------


def test_build_context_bundle_marks_failures(patch_query, monkeypatch):
    # Only provide market data; strat is now sourced via the shared
    # lib.strat.compute_strat_status helper, which we patch directly.
    patch_query(
        "market_data_daily",
        pd.DataFrame([{
            "date": date(2026, 4, 15),
            "close": 500.0, "sma_200": 490.0, "ema_20": 498.0,
            "ema_50": None, "rsi_14": 55.0, "macd": None, "macd_signal": None,
            "macd_histogram": None, "bb_upper": None, "bb_lower": None,
            "bb_pct": None, "atr_14": None, "rvol": None,
            "volatility_20d": 0.15, "price_vs_ema20": 0.004,
            "open": None, "high": None, "low": None, "volume": None,
        }]),
    )
    import lib.strat as strat_mod
    monkeypatch.setattr(
        strat_mod, "compute_strat_status",
        lambda ticker, **kw: {
            "available": True, "ticker": ticker, "date": "2026-04-15",
            "last_candle": "2U", "in_force_combo": None, "strat_setup": True,
            "ftfc_score": 0.3, "ftfc_direction": "bullish",
            "ftfc_labels": {"D": "2U", "W": "1"},
            "trigger_high": 503.0, "trigger_low": 498.0,
        },
    )
    bundle = summarizers.build_context_bundle("SPY")
    assert bundle["ticker"] == "SPY"
    assert bundle["market"]["available"] is True
    assert bundle["strat"]["available"] is True
    assert "options" in bundle["failed_sections"]
    assert "signals" not in bundle["failed_sections"]  # empty=available
    assert "backtest" in bundle["failed_sections"]


def test_build_context_bundle_catches_exceptions(monkeypatch):
    def bad_query(*a, **kw):
        raise RuntimeError("DB down")

    monkeypatch.setattr(summarizers, "_query", bad_query)
    bundle = summarizers.build_context_bundle("SPY")
    # Every section should have failed gracefully
    assert set(bundle["failed_sections"]) >= {
        "market", "strat", "options", "gamma", "signals", "backtest", "catalysts"
    }
    assert bundle["market"]["available"] is False
    # Audit 2026-05-08 G.P2.13: per-section failure reasons must
    # be captured in the bundle so the orchestrator can persist them
    # on the report (no scraping Cloud Logs).
    assert "failed_section_reasons" in bundle
    reasons = bundle["failed_section_reasons"]
    assert "market" in reasons
    assert "DB down" in reasons["market"]
    # Exception-caught reasons get the `exception:` prefix
    assert reasons["market"].startswith("exception: RuntimeError")


# ---------------------------------------------------------------------------
# summarize_gamma_levels
# ---------------------------------------------------------------------------


def test_gamma_levels_extracts_kings_and_regime(patch_query):
    """Synthetic chain → King at the heaviest strike, regime classified."""
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            # Heavy puts at 95 → negative GEX below
            {"option_type": "puts",  "strike": 95.0, "expiration": date(2025, 11, 21),
             "open_interest": 5000, "gamma": 0.05, "vega": 0.10, "delta": -0.30,
             "bid": 0.10, "ask": 0.15, "mark": 0.12, "last_price": 0.13},
            # ATM call/put balanced
            {"option_type": "calls", "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1500, "gamma": 0.06, "vega": 0.10, "delta": 0.50,
             "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55},
            {"option_type": "puts",  "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1500, "gamma": 0.06, "vega": 0.10, "delta": -0.50,
             "bid": 1.45, "ask": 1.55, "mark": 1.50, "last_price": 1.50},
            # Heavy calls at 105 → positive GEX above
            {"option_type": "calls", "strike": 105.0, "expiration": date(2025, 11, 21),
             "open_interest": 5000, "gamma": 0.05, "vega": 0.10, "delta": 0.30,
             "bid": 0.10, "ask": 0.15, "mark": 0.12, "last_price": 0.13},
        ]),
    )
    out = summarizers.summarize_gamma_levels("XYZ")
    assert out["available"] is True
    assert out["spot"] == pytest.approx(100.0, abs=0.5)
    # Spot via parity (mark prices balanced at 100)
    assert out["spot_method"] == "parity"
    # Regime is "unknown" if cumulative GEX doesn't strictly cross zero in
    # the window — that's fine for this fixture; we just verify the field
    # exists and is one of the expected literals.
    assert out["regime"] in ("positive_gamma", "negative_gamma", "unknown")
    # Should have at least one King
    assert len(out["kings"]) >= 1
    assert "chain_size" in out
    assert out["chain_size"] == 4


def test_gamma_levels_unavailable_when_no_chain(patch_query):
    # No data set up → empty DataFrame returned
    out = summarizers.summarize_gamma_levels("ZZZ")
    assert out["available"] is False
    assert "no etf_options_snapshots" in out["reason"]


def test_build_context_bundle_includes_gamma(patch_query):
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            {"option_type": "calls", "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1000, "gamma": 0.05, "vega": 0.10, "delta": 0.50,
             "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55},
            {"option_type": "puts",  "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1000, "gamma": 0.05, "vega": 0.10, "delta": -0.50,
             "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55},
        ]),
    )
    bundle = summarizers.build_context_bundle("XYZ")
    assert "gamma" in bundle
    # Other sections are unavailable in this fixture, but gamma must be the
    # one populated when only chain data is fixtured
    assert bundle["gamma"]["available"] is True


# ---------------------------------------------------------------------------
# summarize_news_sentiment
# ---------------------------------------------------------------------------


def test_news_sentiment_classifies_bullish_bearish_neutral(patch_query):
    """The ±0.15 thresholds are the load-bearing classification — wrong
    bins → wrong AI sentiment-analyst prompt."""
    patch_query("FROM news_sentiment", pd.DataFrame([
        {"title": "very bullish",   "sentiment_score": 0.5,  "relevance_score": 0.9, "source": "AV", "published_ts": "2026-04-25T10:00:00Z"},
        {"title": "mildly bullish", "sentiment_score": 0.16, "relevance_score": 0.7, "source": "AV", "published_ts": "2026-04-25T11:00:00Z"},
        {"title": "edge bullish",   "sentiment_score": 0.15, "relevance_score": 0.8, "source": "AV", "published_ts": "2026-04-25T12:00:00Z"},  # NOT bullish (>, not >=)
        {"title": "neutral",        "sentiment_score": 0.0,  "relevance_score": 0.5, "source": "AV", "published_ts": "2026-04-25T13:00:00Z"},
        {"title": "edge bearish",   "sentiment_score": -0.15,"relevance_score": 0.6, "source": "AV", "published_ts": "2026-04-25T14:00:00Z"},  # NOT bearish (<, not <=)
        {"title": "mildly bearish", "sentiment_score": -0.20,"relevance_score": 0.4, "source": "AV", "published_ts": "2026-04-25T15:00:00Z"},
        {"title": "very bearish",   "sentiment_score": -0.6, "relevance_score": 0.95,"source": "AV", "published_ts": "2026-04-25T16:00:00Z"},
    ]))
    res = summarizers.summarize_news_sentiment("SPY")
    assert res["available"] is True
    assert res["bullish_count"] == 2  # 0.5 and 0.16 only
    assert res["bearish_count"] == 2  # -0.20 and -0.60 only
    assert res["neutral_count"] == 3  # 0.15, 0.0, -0.15
    assert res["article_count"] == 7


def test_news_sentiment_returns_empty_payload_when_no_rows(patch_query):
    """Audit 2026-05-08 G.P2.13: empty news → available + zero-counts
    payload (NOT unavailable). IWM had only 3 articles in 30 days during
    May 2026 — failing the whole section every day for sparse-coverage
    tickers degrades downstream debate. Better to surface 'no recent
    news' to the analyst tier."""
    patch_query("FROM news_sentiment", pd.DataFrame())
    res = summarizers.summarize_news_sentiment("SPY")
    assert res["available"] is True
    assert res["article_count"] == 0
    assert res["bullish_count"] == 0
    assert res["bearish_count"] == 0
    assert res["headlines"] == []
    assert "sparse-coverage" in res["note"]


def test_news_sentiment_returns_top5_by_relevance(patch_query):
    """`headlines` must be the 5 highest-relevance rows, not just the
    first 5 returned."""
    rows = [
        {"title": f"art {i}", "sentiment_score": 0.1,
         "relevance_score": float(i), "source": "AV",
         "published_ts": f"2026-04-25T{i:02d}:00:00Z"}
        for i in range(10)
    ]
    patch_query("FROM news_sentiment", pd.DataFrame(rows))
    res = summarizers.summarize_news_sentiment("SPY")
    titles = [h["title"] for h in res["headlines"]]
    # Top 5 = relevance 9, 8, 7, 6, 5
    assert titles == ["art 9", "art 8", "art 7", "art 6", "art 5"]


def test_news_sentiment_avg_score_drops_none_values(patch_query):
    """One bad row with sentiment_score=None must NOT poison the mean
    or crash the call. The column gets `.dropna().astype(float)` first."""
    patch_query("FROM news_sentiment", pd.DataFrame([
        {"title": "a", "sentiment_score": 0.4,  "relevance_score": 0.9, "source": "AV", "published_ts": "x"},
        {"title": "b", "sentiment_score": None, "relevance_score": 0.5, "source": "AV", "published_ts": "y"},
        {"title": "c", "sentiment_score": 0.0,  "relevance_score": 0.7, "source": "AV", "published_ts": "z"},
    ]))
    res = summarizers.summarize_news_sentiment("SPY")
    # avg of [0.4, 0.0] = 0.2 (None dropped before mean)
    assert res["avg_sentiment_score"] == 0.2
    assert res["article_count"] == 3  # all rows still counted


def test_news_sentiment_as_of_uses_bounded_window(monkeypatch):
    """When `as_of` is set, the SQL switches to the bounded form so
    historical replay (insight reports) doesn't pull future articles."""
    captured: dict = {}

    def fake_query(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    summarizers.summarize_news_sentiment(
        "spy", as_of=date(2026, 4, 25), lookback_hours=72
    )
    assert "CAST(:end_ts AS timestamptz)" in captured["sql"]
    assert captured["params"]["ticker"] == "SPY"  # uppercased
    assert captured["params"]["hours"] == 72
    # end_exclusive = as_of + 1 day = 2026-04-26 (so intraday articles
    # on the as_of date itself are still included via the `<` bound)
    assert "2026-04-26" in captured["params"]["end_ts"]


# ---------------------------------------------------------------------------
# _default_lookback_hours_for — Monday-aware lookback
# ---------------------------------------------------------------------------


def test_default_lookback_72h_on_monday():
    """Monday brief should look back 72h to bridge the weekend gap."""
    # 2026-04-27 is a Monday
    assert summarizers._default_lookback_hours_for(date(2026, 4, 27)) == 72


def test_default_lookback_48h_tuesday_through_friday():
    """Other weekdays use the standard 48h window."""
    assert summarizers._default_lookback_hours_for(date(2026, 4, 28)) == 48  # Tue
    assert summarizers._default_lookback_hours_for(date(2026, 4, 29)) == 48  # Wed
    assert summarizers._default_lookback_hours_for(date(2026, 4, 30)) == 48  # Thu
    assert summarizers._default_lookback_hours_for(date(2026, 5, 1)) == 48  # Fri


def test_default_lookback_48h_saturday_sunday():
    """Weekends — no live brief runs but still 48h if asked."""
    assert summarizers._default_lookback_hours_for(date(2026, 5, 2)) == 48  # Sat
    assert summarizers._default_lookback_hours_for(date(2026, 5, 3)) == 48  # Sun


def test_default_lookback_handles_datetime_input():
    """When passed a datetime (point-in-time replay), use its weekday."""
    from datetime import datetime, timezone
    monday_dt = datetime(2026, 4, 27, 12, 30, tzinfo=timezone.utc)
    assert summarizers._default_lookback_hours_for(monday_dt) == 72


def test_news_sentiment_picks_72h_on_monday(monkeypatch):
    """End-to-end: calling summarize_news_sentiment with no explicit
    lookback on a Monday triggers the 72h default and that value
    reaches the SQL params."""
    captured: dict = {}

    def fake_query(sql, params=None):
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    summarizers.summarize_news_sentiment("IWM", as_of=date(2026, 4, 27))
    assert captured["params"]["hours"] == 72


def test_news_sentiment_picks_48h_on_tuesday(monkeypatch):
    captured: dict = {}

    def fake_query(sql, params=None):
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    summarizers.summarize_news_sentiment("IWM", as_of=date(2026, 4, 28))
    assert captured["params"]["hours"] == 48


def test_news_sentiment_explicit_lookback_overrides_default(monkeypatch):
    """An explicit lookback_hours arg always wins over the weekday default."""
    captured: dict = {}

    def fake_query(sql, params=None):
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    # Monday default would be 72h; explicit 24h must override.
    summarizers.summarize_news_sentiment("IWM", as_of=date(2026, 4, 27), lookback_hours=24)
    assert captured["params"]["hours"] == 24
