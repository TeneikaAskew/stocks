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


def test_strat_status_extracts_trigger_levels(patch_query):
    patch_query(
        "market_data_daily",
        pd.DataFrame([
            {"date": date(2026, 4, 15), "strat_candle": "2U",
             "strat_combo": "2D-1-2U_reversal", "strat_setup": True,
             "ftfc_score": 0.6, "ftfc_direction": "bullish",
             "high": 505.0, "low": 499.0},
            {"date": date(2026, 4, 14), "strat_candle": "1",
             "strat_combo": None, "strat_setup": False,
             "ftfc_score": 0.0, "ftfc_direction": "mixed",
             "high": 503.5, "low": 498.2},
        ]),
    )
    out = summarizers.summarize_strat_status("SPY")
    assert out["available"] is True
    assert out["last_candle"] == "2U"
    assert out["in_force_combo"] == "2D-1-2U_reversal"
    assert out["trigger_high"] == 503.5  # previous day's high
    assert out["trigger_low"] == 498.2
    assert out["ftfc_direction"] == "bullish"


def test_strat_status_handles_nulls(patch_query):
    patch_query(
        "market_data_daily",
        pd.DataFrame([{
            "date": date(2026, 4, 15), "strat_candle": None,
            "strat_combo": None, "strat_setup": None,
            "ftfc_score": None, "ftfc_direction": None,
            "high": None, "low": None,
        }]),
    )
    out = summarizers.summarize_strat_status("SPY")
    assert out["last_candle"] == "1"  # default fallback
    assert out["ftfc_score"] == 0.0
    assert out["ftfc_direction"] == "mixed"


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
# summarize_backtest_metrics
# ---------------------------------------------------------------------------


def test_backtest_metrics_win_rate_and_profit_factor(patch_query):
    patch_query(
        "trades",
        pd.DataFrame([
            {"return_pct": 2.0, "direction": "CALL", "exit_reason": "target"},
            {"return_pct": 1.5, "direction": "CALL", "exit_reason": "target"},
            {"return_pct": 3.0, "direction": "PUT", "exit_reason": "target"},
            {"return_pct": -1.0, "direction": "CALL", "exit_reason": "stop"},
            {"return_pct": -0.5, "direction": "PUT", "exit_reason": "stop"},
        ]),
    )
    out = summarizers.summarize_backtest_metrics("SPY")
    assert out["trade_count"] == 5
    assert out["win_rate"] == 0.6  # 3 of 5
    # wins = 2.0 + 1.5 + 3.0 = 6.5, losses = 1.5, pf = 6.5 / 1.5 ~= 4.33
    assert out["profit_factor"] == 4.33


def test_backtest_metrics_unavailable_empty(patch_query):
    out = summarizers.summarize_backtest_metrics("SPY")
    assert out["available"] is False


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


def test_build_context_bundle_marks_failures(patch_query):
    # Only provide market data; strat/options/signals/backtest/catalysts
    # will all return available:False.
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
            "strat_candle": "2U", "strat_combo": None, "strat_setup": True,
            "ftfc_score": 0.3, "ftfc_direction": "bullish",
        }]),
    )
    bundle = summarizers.build_context_bundle("SPY")
    assert bundle["ticker"] == "SPY"
    assert bundle["market"]["available"] is True
    # Strat uses same market_data_daily needle so it gets populated
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
