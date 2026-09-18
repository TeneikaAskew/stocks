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
    # retrieve_similar_journal uses the non-swallowing sibling; a fixture
    # is exempt from Rule 3.7, so both wrappers get the same canned data.
    monkeypatch.setattr(summarizers, "_query_strict", fake_query)
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
    # The reason names the query's predicate — a row with a close — because
    # "no rows at all" and "only a pre-market placeholder" are the same
    # answer here and guessing between them would be a claim, not a fact.
    assert out == {
        "available": False,
        "reason": "no market_data_daily row with a close for SPY",
    }


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
             "open_interest": 50_000, "implied_volatility": 0.18, "delta": 0.5,
             "snapshot_date": date(2026, 5, 12)},
            {"option_type": "calls", "strike": 505, "volume": 5_000,
             "open_interest": 30_000, "implied_volatility": 0.20, "delta": 0.4,
             "snapshot_date": date(2026, 5, 12)},
            {"option_type": "puts", "strike": 495, "volume": 8_000,
             "open_interest": 40_000, "implied_volatility": 0.22, "delta": -0.45,
             "snapshot_date": date(2026, 5, 12)},
            {"option_type": "puts", "strike": 490, "volume": 3_000,
             "open_interest": 25_000, "implied_volatility": 0.24, "delta": -0.35,
             "snapshot_date": date(2026, 5, 12)},
        ]),
    )
    # as_of=2026-05-13 (Wed) reading 2026-05-12 (Tue) chain = 1 trading day behind = fresh
    out = summarizers.summarize_options_flow("SPY", as_of=date(2026, 5, 13))
    assert out["call_volume"] == 15_000
    assert out["put_volume"] == 11_000
    assert out["put_call_ratio"] == round(11_000 / 15_000, 3)
    assert 500 in out["top_oi_strikes"]
    assert out["max_pain_strike_proxy"] == 500  # highest OI strike
    assert out["vol_weighted_iv"] is not None


def test_options_flow_unavailable(patch_query):
    out = summarizers.summarize_options_flow("SPY")
    assert out["available"] is False


def test_options_flow_stale_chain_returns_unavailable(patch_query):
    """3+ trading days behind as_of → return _unavailable instead of serving."""
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            {"option_type": "calls", "strike": 500, "volume": 10_000,
             "open_interest": 50_000, "implied_volatility": 0.18, "delta": 0.5,
             "snapshot_date": date(2026, 5, 8)},   # Friday
        ]),
    )
    # Wed 5/13 brief reading Fri 5/8 chain = 3 trading days (Fri, Mon, Tue) behind = STALE
    out = summarizers.summarize_options_flow("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is False
    assert "chain stale" in out["reason"]
    assert "3 trading days behind" in out["reason"]


def test_options_flow_monday_morning_friday_chain_is_fresh(patch_query):
    """Standard institutional convention: Mon brief reads Fri-EOD chain (1 trading day)."""
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            {"option_type": "calls", "strike": 100, "volume": 100,
             "open_interest": 1000, "implied_volatility": 0.20, "delta": 0.5,
             "snapshot_date": date(2026, 5, 8)},   # Friday
            {"option_type": "puts", "strike": 100, "volume": 100,
             "open_interest": 1000, "implied_volatility": 0.20, "delta": -0.5,
             "snapshot_date": date(2026, 5, 8)},
        ]),
    )
    # Mon 5/11 brief reading Fri 5/8 chain = 1 trading day = FRESH
    out = summarizers.summarize_options_flow("SPY", as_of=date(2026, 5, 11))
    assert out["available"] is not False  # served, not _unavailable
    assert out["call_volume"] == 100


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
    # Every section should have failed gracefully.
    # `signals` was removed from the bundle on 2026-05-11 to break the
    # signal-monitor feedback loop; it's no longer in the section set.
    assert set(bundle["failed_sections"]) >= {
        "market", "strat", "options", "gamma", "backtest", "catalysts"
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


def _eod_chain_fixture(snapshot_date):
    """Helper: balanced ATM chain that produces a usable gamma summary."""
    return pd.DataFrame([
        # Heavy puts at 95 → negative GEX below
        {"option_type": "puts",  "strike": 95.0, "expiration": date(2025, 11, 21),
         "open_interest": 5000, "gamma": 0.05, "vega": 0.10, "delta": -0.30,
         "bid": 0.10, "ask": 0.15, "mark": 0.12, "last_price": 0.13,
         "snapshot_date": snapshot_date},
        # ATM call/put balanced — spot via parity should land near 100
        {"option_type": "calls", "strike": 100.0, "expiration": date(2025, 11, 21),
         "open_interest": 1500, "gamma": 0.06, "vega": 0.10, "delta": 0.50,
         "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55,
         "snapshot_date": snapshot_date},
        {"option_type": "puts",  "strike": 100.0, "expiration": date(2025, 11, 21),
         "open_interest": 1500, "gamma": 0.06, "vega": 0.10, "delta": -0.50,
         "bid": 1.45, "ask": 1.55, "mark": 1.50, "last_price": 1.50,
         "snapshot_date": snapshot_date},
        # Heavy calls at 105 → positive GEX above
        {"option_type": "calls", "strike": 105.0, "expiration": date(2025, 11, 21),
         "open_interest": 5000, "gamma": 0.05, "vega": 0.10, "delta": 0.30,
         "bid": 0.10, "ask": 0.15, "mark": 0.12, "last_price": 0.13,
         "snapshot_date": snapshot_date},
    ])


def test_gamma_levels_extracts_kings_and_regime(patch_query):
    """Synthetic chain → King at the heaviest strike, regime classified.

    Uses the EOD-fallback path (needle scopes to market_session = 'EOD'
    so phase 1 REALTIME returns empty and phase 2 EOD picks up the
    fixture). Asserts the new data_source field defaults to
    'eod_fallback' when only EOD data is present and within the 2-day
    freshness window.
    """
    patch_query(
        "market_session = 'EOD'",
        _eod_chain_fixture(date(2026, 5, 12)),
    )
    # as_of=2026-05-13 (Wed) reading 2026-05-12 (Tue) chain = 1 trading day behind = fresh
    out = summarizers.summarize_gamma_levels("XYZ", as_of=date(2026, 5, 13))
    assert out["available"] is True
    assert out["data_source"] == "eod_fallback"
    assert out["snapshot_ts"]  # populated (falls back to snapshot_date when ts col absent)
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
    # No data set up → both phase 1 (REALTIME) and phase 2 (EOD)
    # return empty → unavailable.
    out = summarizers.summarize_gamma_levels("ZZZ")
    assert out["available"] is False
    assert "no etf_options_snapshots" in out["reason"]


def test_gamma_levels_realtime_preferred_over_eod(patch_query):
    """REALTIME snapshot present → use it, ignore EOD even if newer date.

    Models a midday brief where both an EOD chain from last night and a
    fresh REALTIME chain from 5 min ago exist; the function must return
    the realtime one with data_source='realtime' and the intraday
    snapshot_ts.
    """
    intraday_ts = pd.Timestamp("2026-05-13 14:32:00", tz="UTC")
    realtime_df = _eod_chain_fixture(date(2026, 5, 13))
    realtime_df["snapshot_ts"] = intraday_ts
    patch_query("market_session = 'REALTIME'", realtime_df)
    # Also seed an EOD row — the function must NOT pick it up because
    # REALTIME is found first.
    patch_query("market_session = 'EOD'", _eod_chain_fixture(date(2026, 5, 12)))

    out = summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is True
    assert out["data_source"] == "realtime"
    # snapshot_ts should reflect the realtime fixture's intraday timestamp,
    # not the EOD fixture's date-only stamp.
    assert "14:32" in out["snapshot_ts"]


def test_gamma_levels_falls_back_to_eod_when_no_realtime(patch_query):
    """No REALTIME rows → fall through to EOD, mark as eod_fallback."""
    patch_query("market_session = 'EOD'", _eod_chain_fixture(date(2026, 5, 12)))
    # Do NOT register a market_session = 'REALTIME' needle — phase 1
    # returns empty → phase 2 picks up the EOD chain.

    out = summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is True
    assert out["data_source"] == "eod_fallback"
    assert out["spot"] == pytest.approx(100.0, abs=0.5)


def test_gamma_levels_stale_eod_returns_stale_fallback(patch_query):
    """3-5 trading days behind as_of → populated summary with stale_fallback flag.

    Pre-Track-1 behavior was to silence the section entirely at 3+ days
    behind. New behavior surfaces the dealer walls so users still get
    context, with `data_source='stale_fallback'` so the brief / analyst
    prompt can render a warning footer.
    """
    patch_query(
        "market_session = 'EOD'",
        _eod_chain_fixture(date(2026, 5, 8)),   # Fri — 3 trading days behind Wed
    )
    out = summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is True
    assert out["data_source"] == "stale_fallback"
    # Summary still populated despite the warning flag
    assert out["spot"] is not None
    assert len(out["kings"]) >= 1


def test_gamma_levels_hard_stale_returns_unavailable(patch_query):
    """>5 trading days behind as_of → return _unavailable (the hard cutoff).

    Dealer positioning a week old is no longer signal — strikes have
    rolled, expirations have been added.
    """
    patch_query(
        "market_session = 'EOD'",
        _eod_chain_fixture(date(2026, 5, 1)),   # ~8 trading days behind Wed 5/13
    )
    out = summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is False
    assert "hard-stale" in out["reason"]


def test_chain_freshness_boundary_2_trading_days_is_fresh():
    """Boundary: exactly 2 trading days behind = served (threshold is > 2)."""
    # Mon → Wed = 2 trading days behind (Mon, Tue, Wed excluded as end)
    reason = summarizers._check_chain_freshness(
        chain_date=date(2026, 5, 11),   # Mon
        target_date=date(2026, 5, 13),  # Wed
    )
    assert reason is None


def test_chain_freshness_3_trading_days_is_stale():
    """Boundary: 3 trading days behind = stale."""
    reason = summarizers._check_chain_freshness(
        chain_date=date(2026, 5, 11),   # Mon
        target_date=date(2026, 5, 14),  # Thu (Mon, Tue, Wed = 3 trading days)
    )
    assert reason is not None
    assert "3 trading days behind" in reason


def test_chain_freshness_accepts_datetime_target():
    """`INSIGHT_AS_OF` ISO timestamps land as tz-aware `datetime` via
    `parse_as_of`. The helper must coerce to `.date()` before counting
    so np.busday_count doesn't raise."""
    from datetime import datetime, timezone
    # Mon Tue Wed = 3 trading days but with datetime input — should still work
    reason = summarizers._check_chain_freshness(
        chain_date=datetime(2026, 5, 11, 16, 0, tzinfo=timezone.utc),
        target_date=datetime(2026, 5, 14, 13, 30, tzinfo=timezone.utc),
    )
    assert reason is not None
    assert "3 trading days behind" in reason

    # Fresh case with datetime should also work
    reason_fresh = summarizers._check_chain_freshness(
        chain_date=datetime(2026, 5, 12, 21, 0, tzinfo=timezone.utc),
        target_date=datetime(2026, 5, 13, 8, 45, tzinfo=timezone.utc),
    )
    assert reason_fresh is None


def test_build_context_bundle_includes_gamma(patch_query):
    patch_query(
        "etf_options_snapshots",
        pd.DataFrame([
            {"option_type": "calls", "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1000, "gamma": 0.05, "vega": 0.10, "delta": 0.50,
             "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55,
             "snapshot_date": date(2026, 5, 12)},
            {"option_type": "puts",  "strike": 100.0, "expiration": date(2025, 11, 21),
             "open_interest": 1000, "gamma": 0.05, "vega": 0.10, "delta": -0.50,
             "bid": 1.50, "ask": 1.60, "mark": 1.55, "last_price": 1.55,
             "snapshot_date": date(2026, 5, 12)},
        ]),
    )
    # Pass explicit as_of so this test doesn't decay over time (the
    # snapshot_date is fixed at 2026-05-12; without as_of it would be
    # compared against date.today() and start failing on 2026-05-15+).
    bundle = summarizers.build_context_bundle("XYZ", as_of=date(2026, 5, 13))
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


# ---------------------------------------------------------------------------
# #822 (audit R5) — summarize_backtest_metrics reads the as-of day's own bar
# ---------------------------------------------------------------------------
#
# The bundle passes `inclusive_today=False` (premarket contract: today's RTH
# bar does not exist yet live, and is look-ahead in replay) to market, strat,
# options and gamma — but `summarize_backtest_metrics` had no such knob and
# always queried `date <= as_of`. On an INSIGHT_AS_OF replay of a past
# morning, "today's pattern" was therefore built from that day's completed
# bar (gap, volume, RSI, close-vs-SMA), i.e. the very session the brief was
# supposed to be forecasting.


def _cutoff_aware_query(monkeypatch, df):
    """A fake `_query` that honours the SQL's `<` / `<=` cutoff against
    `params['cutoff']`, so the test observes which bars the function can
    actually see — not just the SQL text."""
    seen: list[tuple[str, dict]] = []

    def fake_query(sql: str, params=None):
        seen.append((sql, params or {}))
        if "market_data_daily" not in sql:
            return pd.DataFrame()
        cutoff = pd.Timestamp(params["cutoff"]).date()
        dates = pd.to_datetime(df["date"]).dt.date
        if "date < CAST(:cutoff AS date)" in sql:
            out = df[dates < cutoff].reset_index(drop=True)
        else:
            assert "date <= CAST(:cutoff AS date)" in sql, sql
            out = df[dates <= cutoff].reset_index(drop=True)
        if "= ANY(:tickers)" in sql:
            # Cross-ticker pull carries a `ticker` column per source row.
            out = out.assign(ticker="QQQ")
        return out

    monkeypatch.setattr(summarizers, "_query", fake_query)
    # The cross-ticker pull is strict (a DB error must not read as "no
    # analogs"), so both paths need the same cutoff-aware fake or the test
    # would exercise only the same-ticker query.
    monkeypatch.setattr(summarizers, "_query_strict", fake_query)
    return seen


def test_backtest_metrics_premarket_contract_excludes_as_of_bar(monkeypatch):
    from datetime import date as _date
    df = _synth_daily_bars()
    as_of = pd.Timestamp(df.iloc[-1]["date"]).date()
    prior = pd.Timestamp(df.iloc[-2]["date"]).date()
    seen = _cutoff_aware_query(monkeypatch, df)

    out = summarizers.summarize_backtest_metrics(
        "SPY", as_of=as_of, cross_ticker=False, inclusive_today=False)
    assert out["available"] is True, out.get("reason")
    assert out["pattern_today"]["date"] == str(prior), \
        "premarket contract must build the pattern from the prior completed bar"
    assert "date < CAST(:cutoff AS date)" in seen[0][0]
    assert isinstance(as_of, _date)


def test_backtest_metrics_eod_contract_keeps_as_of_bar(monkeypatch):
    """`inclusive_today=True` (explicit EOD analytics) still admits the
    as-of bar — the knob is a contract choice, not a blanket exclusion."""
    df = _synth_daily_bars()
    as_of = pd.Timestamp(df.iloc[-1]["date"]).date()
    seen = _cutoff_aware_query(monkeypatch, df)

    out = summarizers.summarize_backtest_metrics(
        "SPY", as_of=as_of, cross_ticker=False, inclusive_today=True)
    assert out["available"] is True, out.get("reason")
    assert out["pattern_today"]["date"] == str(as_of)
    assert "date <= CAST(:cutoff AS date)" in seen[0][0]


def test_backtest_metrics_default_is_premarket_contract(monkeypatch):
    """The default must match the bundle's default (False): a caller that
    passes only `as_of` gets the no-look-ahead behaviour."""
    df = _synth_daily_bars()
    as_of = pd.Timestamp(df.iloc[-1]["date"]).date()
    prior = pd.Timestamp(df.iloc[-2]["date"]).date()
    _cutoff_aware_query(monkeypatch, df)
    out = summarizers.summarize_backtest_metrics("SPY", as_of=as_of, cross_ticker=False)
    assert out["pattern_today"]["date"] == str(prior)


def test_backtest_metrics_cross_ticker_query_honours_the_same_cutoff(monkeypatch):
    """The cross-ticker analog pull must use the same operator, or the
    as-of bar leaks back in through SPY/QQQ/IWM analogs."""
    df = _synth_daily_bars()
    as_of = pd.Timestamp(df.iloc[-1]["date"]).date()
    seen = _cutoff_aware_query(monkeypatch, df)
    # Membership is resolved separately now; supply it rather than reaching
    # for a database. What this test is about is the cutoff operator on the
    # bar pull, not how the universe was resolved.
    from gcp.fetchers._watchlist import WatchlistMembership

    summarizers.summarize_backtest_metrics(
        "SPY", as_of=as_of, cross_ticker=True, inclusive_today=False,
        universe=WatchlistMembership(
            tickers=("QQQ",), as_of=as_of, owner="default",
            resolution="exact", horizon=None))
    daily_sqls = [s for s, _ in seen if "market_data_daily" in s]
    assert daily_sqls, "no market_data_daily query issued"
    assert all("date <= CAST(:cutoff AS date)" not in s for s in daily_sqls), \
        "a cross-ticker query still admits the as-of bar"


def test_build_context_bundle_forwards_inclusive_today_to_backtest(monkeypatch):
    calls = {}

    def fake_backtest(ticker, lookback_days=90, as_of=None, *, cross_ticker=True,
                      inclusive_today=True, universe=None):
        calls["inclusive_today"] = inclusive_today
        return {"available": False, "reason": "stub"}

    monkeypatch.setattr(summarizers, "summarize_backtest_metrics", fake_backtest)
    monkeypatch.setattr(summarizers, "_query", lambda sql, params=None: pd.DataFrame())
    for name in ("summarize_market_context", "summarize_strat_status",
                 "summarize_options_flow", "summarize_gamma_levels",
                 "summarize_catalysts", "summarize_news_sentiment"):
        monkeypatch.setattr(summarizers, name,
                            lambda *a, **k: {"available": False, "reason": "stub"})
    summarizers.build_context_bundle("SPY", inclusive_today=False)
    assert calls["inclusive_today"] is False


# ---------------------------------------------------------------------------
# Regression: the snapshot_date handed to lib.gamma must be a real date.
#
# `summarize_gamma_levels` used to pass the literal string "latest" whenever
# `as_of` was None — which is every live insight-pipeline run. That string
# travels into `gamma.build_summary` -> `options_greeks.get_rate_and_yield`,
# where it is bound to a Postgres DATE parameter:
#
#   invalid input syntax for type date: "latest"   (SQLSTATE 22007)
#
# `get_rate_and_yield` raises RateLookupError, `gamma.py` catches it and sets
# `gamma_flip = None`, so every live report shipped with the BS-recurved
# zero-gamma level — the regime divider — silently missing. Measured in
# production: 3 occurrences per insight-pipeline run, every weekday since
# the strict rate lookup landed (#994).
# ---------------------------------------------------------------------------


def _capture_build_summary_date(monkeypatch):
    """Record the snapshot_date `summarize_gamma_levels` forwards to gamma."""
    from lib import gamma as gamma_mod

    seen: dict[str, object] = {}
    real = gamma_mod.build_summary

    def spy(*, ticker, snapshot_date, options, **kwargs):
        seen["snapshot_date"] = snapshot_date
        return real(ticker=ticker, snapshot_date=snapshot_date,
                    options=options, **kwargs)

    monkeypatch.setattr(gamma_mod, "build_summary", spy)
    return seen


def _recent_business_day() -> date:
    """Yesterday-or-earlier business day, so the freshness tier stays 'fresh'.

    as_of=None makes summarize_gamma_levels measure staleness against
    date.today(), so a fixed fixture date would age into hard-stale.
    """
    import numpy as _np

    return _np.busday_offset(date.today(), -1, roll="backward").astype(date)


def test_gamma_levels_forwards_a_parseable_date_when_as_of_is_none(
    patch_query, monkeypatch
):
    """as_of=None (the live path) must still yield an ISO date, not a sentinel."""
    chain_date = _recent_business_day()
    patch_query("market_session = 'EOD'", _eod_chain_fixture(chain_date))
    seen = _capture_build_summary_date(monkeypatch)

    out = summarizers.summarize_gamma_levels("SPY")

    assert out["available"] is True
    forwarded = seen["snapshot_date"]
    # The contract get_rate_and_yield depends on: bindable as a DATE.
    assert date.fromisoformat(str(forwarded)[:10]) == chain_date


def test_gamma_levels_uses_the_chain_date_not_the_request_date(
    patch_query, monkeypatch
):
    """An EOD chain is re-curved with ITS OWN day's r/q, not the request's.

    A Wednesday run reading Tuesday's chain must price that chain against
    Tuesday's rates — the snapshot and the rate have to describe the same day.
    """
    chain_date = date(2026, 5, 12)
    patch_query("market_session = 'EOD'", _eod_chain_fixture(chain_date))
    seen = _capture_build_summary_date(monkeypatch)

    summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))

    assert str(seen["snapshot_date"])[:10] == "2026-05-12"


def test_gamma_levels_realtime_forwards_the_snapshot_date(patch_query, monkeypatch):
    """The REALTIME phase must supply a date too — it skips the EOD branch."""
    realtime_df = _eod_chain_fixture(date(2026, 5, 13))
    realtime_df["snapshot_ts"] = pd.Timestamp("2026-05-13 14:32:00", tz="UTC")
    patch_query("market_session = 'REALTIME'", realtime_df)
    seen = _capture_build_summary_date(monkeypatch)

    summarizers.summarize_gamma_levels("SPY")

    assert date.fromisoformat(str(seen["snapshot_date"])[:10]) == date(2026, 5, 13)


# ---------------------------------------------------------------------------
# Regression: the reflection-memory query must be a legal bound statement.
#
# `:vec::vector` is not a cast of the bind parameter — SQLAlchemy's text()
# parser reads `:vec:` and keeps `:vec::vector` verbatim in the SQL while
# declaring a phantom parameter named `ve`. Postgres then sees a literal
# colon and rejects the whole statement:
#
#   syntax error at or near ":"   (SQLSTATE 42601, position 77)
#
# `_query` swallows that (CLAUDE.md Rule 3.7), so retrieve_similar_journal
# returned [] and every insight report lost its journal reflection section
# with no visible failure. Measured: 3 per insight-pipeline run, every
# weekday. `CAST(:vec AS vector)` is the spelling text() parses correctly.
# ---------------------------------------------------------------------------


def test_retrieve_similar_journal_sql_binds_every_parameter(patch_query):
    """The emitted SQL must declare exactly the params the call supplies."""
    import sqlalchemy

    captured: dict[str, object] = {}

    def capture(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return pd.DataFrame()

    import lib.agents.summarizers as mod
    orig = mod._query_strict
    mod._query_strict = capture
    try:
        summarizers.retrieve_similar_journal("SPY", [0.1] * 768, k=5)
    finally:
        mod._query_strict = orig

    stmt = sqlalchemy.text(str(captured["sql"]))
    assert set(stmt._bindparams) == set(captured["params"]), (
        "bind parameters parsed out of the SQL must match the params passed in"
    )


def test_retrieve_similar_journal_sql_leaves_no_literal_placeholder(patch_query):
    """Compiling must consume every ':name' — a leftover is the 42601."""
    import sqlalchemy
    from sqlalchemy.dialects import postgresql

    captured: dict[str, object] = {}

    def capture(sql, params=None):
        captured["sql"] = sql
        return pd.DataFrame()

    import lib.agents.summarizers as mod
    orig = mod._query_strict
    mod._query_strict = capture
    try:
        summarizers.retrieve_similar_journal("SPY", [0.1] * 768, k=5)
    finally:
        mod._query_strict = orig

    compiled = str(
        sqlalchemy.text(str(captured["sql"])).compile(
            dialect=postgresql.dialect(paramstyle="format")
        )
    )
    assert ":vec" not in compiled
    assert compiled.count("%s") == 4, (
        f"expected vec twice plus ticker and k, got: {compiled}"
    )


def test_retrieve_similar_journal_surfaces_db_failure(monkeypatch):
    """A DB failure must raise, not read as 'no similar trades'.

    The swallowing `_query` is what let the malformed cast above look like
    an empty result for a week. The orchestrator wraps this call in its own
    handler, so raising here costs nothing and names the failure in the log.
    """
    def boom(sql, params=None):
        raise RuntimeError("Cloud SQL unreachable")

    monkeypatch.setattr(summarizers, "_query_strict", boom)
    with pytest.raises(RuntimeError, match="Cloud SQL unreachable"):
        summarizers.retrieve_similar_journal("SPY", [0.1] * 768, k=5)


# ---------------------------------------------------------------------------
# Regression: the live path must not read the pre-market placeholder row.
#
# The daily fetcher writes a row for the current trading day at ~8:30 ET
# carrying only the pre_* columns; open/high/low/close/volume and every
# indicator are NULL until the 11 PM ET fetcher fills them. The replay path
# already avoids that row (`date < :as_of`) and PR #323 taught
# summarize_backtest_metrics to walk back past it — but the LIVE path
# (as_of=None) applies no date bound at all, so `ORDER BY date DESC LIMIT 1`
# selects the placeholder and every daily field comes back None.
#
# Downstream that becomes `float(None or None or 0.0)` in
# trade_planner.context_from_bundle, `safe_atr()` returns `0.0 * 0.01`, and
# the first `/ atr` raises. Measured in production: "deterministic plan
# compute failed: float division by zero", 3 per insight-pipeline run, every
# weekday — leaving persona_plans empty and handing the report's headline
# entry/stop/targets back to the LLM, which is the exact hallucination
# surface compute_persona_plans exists to close.
# ---------------------------------------------------------------------------


def _placeholder_row(d: date) -> dict:
    """Today's 8:30 ET row: pre_* populated, everything else NULL."""
    return {
        "date": d, "open": None, "high": None, "low": None, "close": None,
        "volume": None, "sma_200": None, "ema_20": None, "ema_50": None,
        "rsi_14": None, "macd": None, "macd_signal": None,
        "macd_histogram": None, "bb_upper": None, "bb_lower": None,
        "bb_pct": None, "atr_14": None, "rvol": None, "volatility_20d": None,
        "price_vs_ema20": None,
        "pre_high": 766.18, "pre_low": 757.77, "pre_vwap": 759.37,
        "pre_volume": 4_200_000, "gap_pct": -0.649, "pre_range_atr": 0.4,
    }


def _completed_row(d: date) -> dict:
    """Yesterday's finished bar."""
    return {
        "date": d, "open": 762.0, "high": 766.0, "low": 760.0, "close": 764.29,
        "volume": 71_000_000, "sma_200": 714.23, "ema_20": 760.1,
        "ema_50": 750.0, "rsi_14": 58.0, "macd": 1.2, "macd_signal": 0.9,
        "macd_histogram": 0.3, "bb_upper": 772.0, "bb_lower": 748.0,
        "bb_pct": 0.66, "atr_14": 6.21, "rvol": 1.05, "volatility_20d": 0.14,
        "price_vs_ema20": 0.005,
        "pre_high": 758.0, "pre_low": 752.0, "pre_vwap": 755.0,
        "pre_volume": 3_000_000, "gap_pct": 0.11, "pre_range_atr": 0.2,
    }


def _market_query_router(monkeypatch, *, placeholder_present: bool):
    """Stand in for market_data_daily with a placeholder row on top.

    Serves whichever row the SQL actually asks for, so the test measures
    the query's selectivity rather than a canned answer.
    """
    today, yesterday = date(2026, 9, 14), date(2026, 9, 11)
    rows = [_completed_row(yesterday)]
    if placeholder_present:
        rows.append(_placeholder_row(today))

    def fake_query(sql: str, params=None):
        if "market_data_daily" not in sql:
            return pd.DataFrame()
        frame = pd.DataFrame(rows).sort_values("date", ascending=False)
        if "close IS NOT NULL" in sql:
            frame = frame[frame["close"].notna()]
        if params and "as_of" in params:
            as_of = pd.to_datetime(params["as_of"]).date()
            if "date = :as_of" in sql:
                frame = frame[frame["date"] == as_of]
            elif "date < :as_of" in sql:
                frame = frame[frame["date"] < as_of]
            elif "date <= :as_of" in sql:
                frame = frame[frame["date"] <= as_of]
        return frame.head(1).reset_index(drop=True)

    monkeypatch.setattr(summarizers, "_query", fake_query)


def test_market_context_live_skips_the_premarket_placeholder(monkeypatch):
    """as_of=None must return yesterday's completed bar, not today's NULLs."""
    _market_query_router(monkeypatch, placeholder_present=True)

    out = summarizers.summarize_market_context("SPY")

    assert out["available"] is True
    assert out["close"] == 764.29
    assert out["atr_14"] == 6.21
    assert out["sma_200"] == 714.23
    assert out["date"].startswith("2026-09-11")


def test_market_context_live_still_takes_premarket_from_todays_row(monkeypatch):
    """The pre_* overlay is the whole reason today's row is read at all.

    A day-old pre_high is worse than none — the docstring's replay
    contract says so, and the live path owes the same guarantee.
    """
    _market_query_router(monkeypatch, placeholder_present=True)

    out = summarizers.summarize_market_context("SPY")

    assert out["premarket"]["pre_high"] == 766.18
    assert out["premarket"]["pre_low"] == 757.77
    assert out["premarket"]["gap_pct"] == -0.649


def test_market_context_live_unchanged_when_no_placeholder_exists(monkeypatch):
    """Before the 8:30 fetcher runs, the latest row IS the completed bar."""
    _market_query_router(monkeypatch, placeholder_present=False)

    out = summarizers.summarize_market_context("SPY")

    assert out["close"] == 764.29
    assert out["premarket"]["pre_high"] == 758.0
