"""Phase 0.5 — hermetic tests for the signal-quality report pipeline.

No Cloud SQL, no live network. Synthetic bars and dict source rows.

Coverage:
  1. classify() — every label, including INSUFFICIENT_DATA / NaN handling
  2. classify() — boundary values exactly at CLEAN_THRESHOLD/NOISE_THRESHOLD
  3. best_clean_timeframe — picks the SHORTEST clean tf
  4. determine_status — historical always 'final'; rolling 'pending'
     when any tf missing, 'final' when all present
  5. extend_returns_from_intraday — CALL favorable = max(High); PUT = min(Low)
  6. extend_returns_from_intraday — empty bars and pre-entry bars handled
  7. compute_atr_pct — None when too few bars, fraction-of-price otherwise
  8. compute_metrics_for_signal — full pipeline on a synthetic row
  9. compute_metrics_for_signal — mfe_60m_atrs is None when ATR unavailable
 10. parse_args — required flags and defaults
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.signal_quality_report import (  # noqa: E402
    CLEAN_THRESHOLD,
    EXTENDED_TFS_MIN,
    NOISE_THRESHOLD,
    _resolve_window,
    _slice_intraday,
    best_clean_timeframe,
    build_quality_report_embed,
    classify,
    compute_atr_pct,
    compute_metrics_for_signal,
    determine_status,
    extend_returns_from_intraday,
    main,
    parse_args,
    process_ticker_batch,
)


# ── 1) classify — every label ──────────────────────────────────────────

def test_classify_clean_hit():
    assert classify(0.010) == "CLEAN_HIT"
    assert classify(CLEAN_THRESHOLD) == "CLEAN_HIT"   # boundary


def test_classify_wrong_direction():
    assert classify(-0.010) == "WRONG_DIRECTION"
    assert classify(-CLEAN_THRESHOLD) == "WRONG_DIRECTION"  # boundary


def test_classify_noise_below_noise_threshold():
    assert classify(0.001) == "NOISE"
    assert classify(-0.001) == "NOISE"


def test_classify_mixed_between_noise_and_clean():
    """A return between NOISE_THRESHOLD and CLEAN_THRESHOLD is MIXED."""
    mid = (NOISE_THRESHOLD + CLEAN_THRESHOLD) / 2
    assert classify(mid) == "MIXED"
    assert classify(-mid) == "MIXED"


def test_classify_insufficient_data_on_none():
    assert classify(None) == "INSUFFICIENT_DATA"


def test_classify_insufficient_data_on_nan():
    assert classify(float("nan")) == "INSUFFICIENT_DATA"


# ── 2) best_clean_timeframe ────────────────────────────────────────────

def test_best_clean_timeframe_picks_shortest():
    """Multiple clean timeframes → shortest wins."""
    rets = {5: 0.001, 15: 0.010, 30: 0.012, 60: 0.020}
    assert best_clean_timeframe(rets) == "15m"


def test_best_clean_timeframe_none_clean_returns_none():
    rets = {5: 0.001, 15: 0.001, 30: -0.001, 60: 0.002}
    assert best_clean_timeframe(rets) is None


def test_best_clean_timeframe_includes_all_input_tfs():
    """Doesn't restrict to a fixed list — uses whatever keys are in the dict."""
    rets = {5: 0.001, 90: 0.010, 240: 0.015}
    assert best_clean_timeframe(rets) == "90m"


# ── 3) determine_status ────────────────────────────────────────────────

def test_determine_status_historical_always_final():
    assert determine_status({5: None, 60: None}, mode="historical") == "final"
    assert determine_status({5: 0.001}, mode="historical") == "final"


def test_determine_status_rolling_final_when_all_present():
    rets = {tf: 0.001 for tf in (5, 15, 30, 60, 90, 120, 240)}
    assert determine_status(rets, mode="rolling") == "final"


def test_determine_status_rolling_pending_on_missing():
    rets = {5: 0.001, 60: 0.002, 240: None}
    assert determine_status(rets, mode="rolling") == "pending"


def test_determine_status_rolling_pending_on_nan():
    rets = {5: 0.001, 60: float("nan")}
    assert determine_status(rets, mode="rolling") == "pending"


# ── 4) extend_returns_from_intraday ────────────────────────────────────

def _make_synthetic_intraday(entry_time: pd.Timestamp,
                             entry_price: float = 100.0,
                             bars: int = 250) -> pd.DataFrame:
    """One bar per minute starting at entry_time. Price drifts up by
    1¢/min, with each bar's High = price+0.05, Low = price-0.05."""
    times = pd.date_range(entry_time, periods=bars, freq="1min")
    closes = entry_price + np.arange(bars) * 0.01
    return pd.DataFrame({
        "Time":  times,
        "Open":  closes - 0.005,
        "High":  closes + 0.05,
        "Low":   closes - 0.05,
        "Close": closes,
    })


def test_extend_returns_call_uses_max_high():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    bars = _make_synthetic_intraday(entry)
    out = extend_returns_from_intraday(bars, entry, entry_price=100.0, direction="CALL")
    # window_end = entry + Nm is INCLUSIVE, so bar at index N (= entry + N min) is in.
    # Bar N close = 100 + N*0.01; high = close + 0.05.
    assert out[90]  == pytest.approx((100.0 + 90 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)
    assert out[120] == pytest.approx((100.0 + 120 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)
    assert out[240] == pytest.approx((100.0 + 240 * 0.01 + 0.05 - 100.0) / 100.0, rel=1e-6)


def test_extend_returns_put_uses_min_low():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    bars = _make_synthetic_intraday(entry)
    out = extend_returns_from_intraday(bars, entry, entry_price=100.0, direction="PUT")
    # The low at entry minute = 100 - 0.05 = 99.95 → favorable PUT excursion
    expected = (100.0 - 99.95) / 100.0
    assert out[90] == pytest.approx(expected, rel=1e-6)


def test_extend_returns_empty_intraday_returns_none_for_each_tf():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    out = extend_returns_from_intraday(pd.DataFrame(), entry, 100.0, "CALL")
    assert out == {90: None, 120: None, 240: None}


def test_extend_returns_drops_pre_entry_bars():
    """Bars before entry_time must not influence the favorable excursion."""
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    pre = _make_synthetic_intraday(entry - timedelta(minutes=60), bars=60)
    pre["High"] = 200.0  # huge spike *before* entry — must be ignored
    post = _make_synthetic_intraday(entry, bars=250)
    bars = pd.concat([pre, post], ignore_index=True)
    out = extend_returns_from_intraday(bars, entry, 100.0, "CALL")
    # Pre-entry $200 high must NOT bleed into the result
    assert out[90] is not None
    assert out[90] < 0.05  # would be ~1.0 if pre-entry bar leaked


# ── 5) compute_atr_pct ─────────────────────────────────────────────────

def test_compute_atr_pct_returns_none_with_too_few_bars():
    bars = pd.DataFrame({
        "High":  [101] * 5,
        "Low":   [99] * 5,
        "Close": [100] * 5,
    })
    assert compute_atr_pct(bars, 100.0, period=14) is None


def test_compute_atr_pct_returns_fraction_of_price():
    bars = pd.DataFrame({
        "High":  [101.0] * 30,
        "Low":   [99.0] * 30,
        "Close": [100.0] * 30,
    })
    out = compute_atr_pct(bars, 100.0, period=14)
    # All bars have TR = 2.0; ATR = 2.0; ATR/price = 0.02
    assert out == pytest.approx(0.02, rel=1e-3)


def test_compute_atr_pct_none_on_zero_entry_price():
    bars = pd.DataFrame({"High": [101] * 30, "Low": [99] * 30, "Close": [100] * 30})
    assert compute_atr_pct(bars, 0.0) is None


def test_compute_atr_pct_accepts_last_column_alias():
    """Production-realistic fixture: gcp/historical_signals.load_intraday_bars
    aliases the SQL `close` column as `Last` (per MarketAnalyzer's column
    convention). When that's the only close-price column on the DataFrame,
    compute_atr_pct must NOT raise KeyError('Close')."""
    bars = pd.DataFrame({
        "Time":  pd.date_range("2026-04-29 14:30", periods=30, freq="1min"),
        "High":  [101.0] * 30,
        "Low":   [99.0]  * 30,
        "Last":  [100.0] * 30,    # NOT 'Close' — production column shape
    })
    out = compute_atr_pct(bars, 100.0, period=14)
    assert out == pytest.approx(0.02, rel=1e-3)


def test_compute_atr_pct_prefers_close_when_both_present():
    """If both Close and Last exist (MarketAnalyzer-enriched DF), use
    Close — that's the canonical column when it's available."""
    bars = pd.DataFrame({
        "High":  [101.0] * 30,
        "Low":   [99.0]  * 30,
        "Close": [100.0] * 30,    # used
        "Last":  [50.0]  * 30,    # would yield ATR/price = 0.04 if used
    })
    out = compute_atr_pct(bars, 100.0, period=14)
    assert out == pytest.approx(0.02, rel=1e-3)


def test_compute_atr_pct_returns_none_when_no_close_column():
    """Defensive: if neither Close nor Last is present, return None
    rather than raise — keeps the pipeline running on weird inputs."""
    bars = pd.DataFrame({
        "High": [101.0] * 30,
        "Low":  [99.0]  * 30,
    })
    assert compute_atr_pct(bars, 100.0) is None


# ── 6) compute_metrics_for_signal end-to-end ───────────────────────────

def test_compute_metrics_for_signal_full_pipeline():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    intraday = _make_synthetic_intraday(entry, bars=250)
    lookback = pd.DataFrame({
        "High":  [101.0] * 30,
        "Low":   [99.0] * 30,
        "Close": [100.0] * 30,
    })
    # historical_signals stores PERCENTAGE POINTS (0.06 = 0.06%), the unit
    # lib/trading_analysis.py writes. #1154: this row once fed fractions,
    # the unit the code assumed, so the test agreed with the bug.
    src = {
        "ticker":         "SPY",
        "entry_time":     entry,
        "strategy":       "momentum",
        "trade_type":     "CALL",
        "entry_price":    100.0,
        "return_5min":    0.06,      # 0.06% -> NOISE
        "return_15min":   0.40,      # 0.40% -> MIXED
        "return_30min":   0.70,      # 0.70% -> CLEAN_HIT
        "return_60min":   1.50,      # 1.50% -> CLEAN_HIT
    }
    m = compute_metrics_for_signal(src, intraday=intraday,
                                    intraday_lookback=lookback, mode="historical")
    assert m.ticker == "SPY"
    assert m.strategy == "momentum"
    assert m.cls_5m == "NOISE"
    assert m.cls_15m == "MIXED"
    assert m.cls_30m == "CLEAN_HIT"
    assert m.cls_60m == "CLEAN_HIT"
    # extended timeframes: synthetic bars produce favorable returns > CLEAN_THRESHOLD
    assert m.cls_90m == "CLEAN_HIT"
    assert m.cls_240m == "CLEAN_HIT"
    assert m.best_tf == "30m"   # shortest clean
    assert m.return_60m == pytest.approx(0.015, rel=1e-9)   # stored as a fraction
    assert m.atr_5m_pct == pytest.approx(0.02, rel=1e-3)
    # mfe_60m_atrs = 0.015 / 0.02 = 0.75
    assert m.mfe_60m_atrs == pytest.approx(0.75, rel=1e-3)
    assert m.status == "final"  # historical mode


def test_source_returns_reach_classify_as_fractions_end_to_end():
    """#1154 unit contract, writer to reader, with nothing mocked but the
    catalyst lookup.

    MarketAnalyzer.generate_technical_signals writes return_*min in
    PERCENTAGE POINTS (`* 100`); map_signals_to_table carries them into
    the historical_signals shape unchanged; compute_metrics_for_signal must
    hand classify() a FRACTION, the unit CLEAN_THRESHOLD and
    NOISE_THRESHOLD are written in.

    The bars rise 0.2% over the hour after entry: a 0.002 fraction, NOISE
    under the 0.003 floor. Read raw, the same move arrives as 0.2 and
    clears the 0.005 CLEAN bar forty times over, which is what production
    did on every 5/15/30/60m row it wrote.
    """
    from lib.trading_analysis import MarketAnalyzer
    from scripts.run_historical_signals import map_signals_to_table

    n = 120
    last = 100.0 + np.arange(n) * (100.0 * 0.002 / 60)   # +0.2% per 60 bars
    bars = pd.DataFrame({
        "Time": pd.date_range("2026-04-29 13:30", periods=n, freq="1min", tz="UTC"),
        "Last": last,
        "Volume": 1_000,
        # Enough CALL conditions to clear the gate (>= 5, core >= 2):
        "RSI14_W": 35.0,                 # core: inside (25, 50)
        "StochRSI_K": 50.0,
        "VWAP": 90.0, "EMA9": 90.0,      # core: price above both
        "RVol_Recent_20": 1.5,           # confirming: > 1.2
        "ATR_Expansion": 1.3,            # confirming: > 1.15
    })
    signals = MarketAnalyzer().generate_technical_signals(bars)
    assert not signals.empty
    with patch("lib.strategies.catalyst_proximity.get_catalyst_context",
               return_value={}):
        rows = map_signals_to_table(signals, "SPY", strategy="momentum")

    row = rows.iloc[0].to_dict()
    i = int(bars.index[bars["Time"] == row["entry_time"]][0])
    entry_price = float(bars["Last"].iloc[i])
    m = compute_metrics_for_signal(row, mode="historical")

    for tf, got in ((5, m.return_5m), (15, m.return_15m),
                    (30, m.return_30m), (60, m.return_60m)):
        # The favourable excursion as a FRACTION, measured on the bars.
        want = (float(bars["Last"].iloc[i + 1:i + 1 + tf].max()) - entry_price) / entry_price
        assert got == pytest.approx(want, rel=1e-9), f"{tf}m"
    assert m.return_60m == pytest.approx(0.002, rel=1e-3)
    assert m.cls_60m == "NOISE"


def test_compute_metrics_for_signal_no_intraday_marks_extended_insufficient():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker":         "SPY",
        "entry_time":     entry,
        "strategy":       "momentum",
        "trade_type":     "CALL",
        "entry_price":    100.0,
        "return_5min":    0.001,
        "return_15min":   0.001,
        "return_30min":   0.001,
        "return_60min":   0.001,
    }
    m = compute_metrics_for_signal(src, intraday=None, intraday_lookback=None,
                                    mode="historical")
    assert m.cls_90m == "INSUFFICIENT_DATA"
    assert m.cls_120m == "INSUFFICIENT_DATA"
    assert m.cls_240m == "INSUFFICIENT_DATA"
    assert m.atr_5m_pct is None
    assert m.mfe_60m_atrs is None    # can't normalize without ATR


def test_compute_metrics_for_signal_rolling_mode_pending_when_extended_missing():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker": "SPY", "entry_time": entry, "strategy": "momentum",
        "trade_type": "CALL", "entry_price": 100.0,
        "return_5min": 0.001, "return_15min": 0.001,
        "return_30min": 0.001, "return_60min": 0.001,
    }
    m = compute_metrics_for_signal(src, intraday=None, intraday_lookback=None,
                                    mode="rolling")
    assert m.status == "pending"   # missing 90/120/240


def test_compute_metrics_for_signal_default_strategy_momentum():
    """Backwards-compat: rows without strategy default to 'momentum'."""
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = {
        "ticker": "SPY", "entry_time": entry,
        "trade_type": "CALL", "entry_price": 100.0,
        "return_5min": 0.001,
    }
    m = compute_metrics_for_signal(src, mode="historical")
    assert m.strategy == "momentum"


# ── 7) parse_args ──────────────────────────────────────────────────────

def test_parse_args_historical_requires_start_end():
    args = parse_args(["--mode", "historical", "--start", "2026-04-01", "--end", "2026-05-01"])
    assert args.mode == "historical"
    assert args.start == "2026-04-01"
    assert args.end == "2026-05-01"


def test_parse_args_rolling_default_lookback_4h():
    args = parse_args(["--mode", "rolling"])
    assert args.mode == "rolling"
    assert args.lookback_hours == 4


def test_parse_args_strategy_default_all():
    args = parse_args(["--mode", "rolling"])
    assert args.strategy == "all"


def test_parse_args_rejects_unknown_mode():
    with pytest.raises(SystemExit):
        parse_args(["--mode", "garbage"])


def test_parse_args_accepts_lookback_days():
    args = parse_args(["--mode", "historical", "--lookback-days", "2"])
    assert args.mode == "historical"
    assert args.lookback_days == 2


# ── _resolve_window: CLI → datetime window translation ────────────────

def test_resolve_window_rolling_uses_lookback_hours():
    args = parse_args(["--mode", "rolling", "--lookback-hours", "6"])
    start, end = _resolve_window(args)
    assert (end - start) == timedelta(hours=6)


def test_resolve_window_historical_with_explicit_dates():
    args = parse_args(["--mode", "historical", "--start", "2026-04-01", "--end", "2026-05-01"])
    start, end = _resolve_window(args)
    assert start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_resolve_window_historical_with_lookback_days():
    args = parse_args(["--mode", "historical", "--lookback-days", "7"])
    start, end = _resolve_window(args)
    assert (end - start) == timedelta(days=7)


def test_resolve_window_historical_without_dates_or_lookback_raises():
    """The bug that caused the nightly scheduler to fail with exit 2:
    historical mode with no --start/--end and no --lookback-days."""
    args = parse_args(["--mode", "historical"])
    with pytest.raises(ValueError, match="lookback-days"):
        _resolve_window(args)


# ── _slice_intraday: in-memory window cut for one signal ──────────────

def test_slice_intraday_forward_includes_entry_minute_through_max_tf():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    full = _make_synthetic_intraday(entry - timedelta(minutes=120), bars=400)
    forward, lookback = _slice_intraday(full, entry)
    assert forward["Time"].min() == entry
    # Forward window is entry through entry + max_tf (240m) + 5m headroom
    assert forward["Time"].max() <= entry + timedelta(minutes=max(EXTENDED_TFS_MIN) + 5)


def test_slice_intraday_lookback_excludes_entry_minute():
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    full = _make_synthetic_intraday(entry - timedelta(minutes=120), bars=200)
    forward, lookback = _slice_intraday(full, entry)
    # Lookback is [entry-120m, entry) — entry is NOT included in lookback
    assert lookback["Time"].max() < entry
    # Forward starts AT entry
    assert forward["Time"].min() == entry


def test_slice_intraday_handles_entries_at_window_edge():
    """If entry_t is at the very end of the cached DataFrame, forward
    is empty (no future bars yet) but lookback should still be intact."""
    entry = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    full = _make_synthetic_intraday(entry - timedelta(minutes=60), bars=61)  # ends at entry
    forward, lookback = _slice_intraday(full, entry)
    assert len(forward) == 1   # just the entry-minute bar
    assert not lookback.empty


# ── process_ticker_batch: per-ticker batched processing ───────────────

def _three_signals_for_ticker(ticker: str, base_time: pd.Timestamp) -> pd.DataFrame:
    """Three CALL signals 30 minutes apart for one ticker."""
    return pd.DataFrame([
        {
            "ticker": ticker, "entry_time": base_time + timedelta(minutes=30 * i),
            "strategy": "momentum", "trade_type": "CALL", "entry_price": 100.0,
            "return_5min": 0.001, "return_15min": 0.002,
            "return_30min": 0.005, "return_60min": 0.008,
        }
        for i in range(3)
    ])


def test_process_ticker_batch_makes_one_intraday_fetch_per_ticker():
    """The whole point of the refactor: N signals for the same ticker
    must trigger exactly ONE call to fetch_intraday_window — not N."""
    base = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    group = _three_signals_for_ticker("SPY", base)
    # Cache covers earliest_entry-120m to latest_entry+max_tf+5m
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)

    fetch_calls: list[dict] = []
    def _capture(_engine, ticker, start, end):
        fetch_calls.append({"ticker": ticker, "start": start, "end": end})
        return cache

    with patch("scripts.signal_quality_report.fetch_intraday_window",
                side_effect=_capture), \
         patch("scripts.signal_quality_report.upsert_signal_metrics",
                return_value=3):
        processed, upserted, _ = process_ticker_batch(
            engine=object(), ticker="SPY", group=group,
            mode="historical", dry_run=False,
        )

    assert processed == 3
    assert upserted == 3
    assert len(fetch_calls) == 1, (
        f"expected ONE fetch_intraday_window call per ticker, got {len(fetch_calls)}"
    )
    # The single fetch must cover ALL signals' windows
    f = fetch_calls[0]
    assert f["ticker"] == "SPY"
    assert f["start"] <= base - timedelta(minutes=120)
    assert f["end"] >= base + timedelta(minutes=30 * 2 + max(EXTENDED_TFS_MIN))


def test_process_ticker_batch_skips_when_no_intraday_bars():
    """If the intraday fetch returns empty (e.g. ticker not yet ingested),
    the batch logs and skips — does NOT crash the whole job."""
    base = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    group = _three_signals_for_ticker("WEIRD", base)

    with patch("scripts.signal_quality_report.fetch_intraday_window",
                return_value=pd.DataFrame()), \
         patch("scripts.signal_quality_report.upsert_signal_metrics") as mock_upsert:
        processed, upserted, counts = process_ticker_batch(
            engine=object(), ticker="WEIRD", group=group,
            mode="historical", dry_run=False,
        )

    assert processed == 3        # we count signals attempted
    assert upserted == 0          # but nothing got written
    assert mock_upsert.call_count == 0


def test_process_ticker_batch_dry_run_does_not_upsert():
    base = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    group = _three_signals_for_ticker("SPY", base)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)

    with patch("scripts.signal_quality_report.fetch_intraday_window",
                return_value=cache), \
         patch("scripts.signal_quality_report.upsert_signal_metrics") as mock_upsert:
        processed, upserted, _ = process_ticker_batch(
            engine=object(), ticker="SPY", group=group,
            mode="historical", dry_run=True,
        )

    assert processed == 3
    assert upserted == 0
    assert mock_upsert.call_count == 0


def test_process_ticker_batch_empty_group_returns_zeros():
    processed, upserted, counts = process_ticker_batch(
        engine=object(), ticker="SPY", group=pd.DataFrame(),
        mode="historical", dry_run=False,
    )
    assert processed == 0
    assert upserted == 0
    assert counts == {}


# ── main(): end-to-end orchestration with batching ────────────────────

def test_main_batches_one_intraday_fetch_per_ticker():
    """Acceptance test for the perf fix: 3 tickers × 3 signals = 9 source
    rows must produce exactly 3 fetch_intraday_window calls — not 9, not 18."""
    base = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = pd.concat([
        _three_signals_for_ticker("SPY", base),
        _three_signals_for_ticker("QQQ", base),
        _three_signals_for_ticker("IWM", base),
    ], ignore_index=True)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)

    fetch_calls: list[str] = []
    def _capture(_engine, ticker, start, end):
        fetch_calls.append(ticker)
        return cache

    with patch("scripts.signal_quality_report.get_engine", create=True,
                return_value=object()), \
         patch("gcp.database.get_engine", return_value=object()), \
         patch("scripts.signal_quality_report.fetch_source_rows",
                return_value=src), \
         patch("scripts.signal_quality_report.fetch_intraday_window",
                side_effect=_capture), \
         patch("scripts.signal_quality_report.upsert_signal_metrics",
                return_value=3):
        rc = main([
            "--mode", "historical",
            "--start", "2026-04-29", "--end", "2026-04-30",
            "--skip-freshness-check",
        ])

    assert rc == 0
    assert len(fetch_calls) == 3, (
        f"expected 3 fetches (one per ticker), got {len(fetch_calls)}: {fetch_calls}"
    )
    assert sorted(fetch_calls) == ["IWM", "QQQ", "SPY"]


def test_main_historical_without_dates_or_lookback_returns_2():
    """Repro for the nightly scheduler bug: --mode=historical with no
    window specifier must exit non-zero with a clear error log, not
    silently drift behavior."""
    with patch("gcp.database.get_engine", return_value=object()):
        rc = main(["--mode", "historical"])
    assert rc == 2


def test_main_historical_with_lookback_days_succeeds():
    """The fix path: nightly scheduler can pass --lookback-days=2."""
    base = pd.Timestamp("2026-04-29 14:30:00", tz="UTC")
    src = _three_signals_for_ticker("SPY", base)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)

    with patch("scripts.signal_quality_report.get_engine", create=True,
                return_value=object()), \
         patch("gcp.database.get_engine", return_value=object()), \
         patch("scripts.signal_quality_report.fetch_source_rows",
                return_value=src), \
         patch("scripts.signal_quality_report.fetch_intraday_window",
                return_value=cache), \
         patch("scripts.signal_quality_report.upsert_signal_metrics",
                return_value=3):
        rc = main(["--mode", "historical", "--lookback-days", "2",
                   "--skip-freshness-check"])

    assert rc == 0


# ── build_quality_report_embed — Discord summary ───────────────────────

def test_build_quality_report_embed_basic():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 8, tzinfo=timezone.utc)
    counts = {'CLEAN_HIT': 6, 'MIXED': 2, 'NOISE': 1, 'WRONG_DIRECTION': 1}
    embed = build_quality_report_embed(start, end, 'historical', 10, 10, counts)
    assert embed['title'] == 'Signal Quality Report'
    desc = embed['description']
    assert '2026-05-01 → 2026-05-08' in desc
    assert 'mode `historical`' in desc
    assert 'Processed **10** signals' in desc
    # decided = 6+2+1+1 = 10, clean rate = 6/10 = 60.0%
    assert 'Clean rate **60.0%** (6/10 decided)' in desc
    # 60% >= 50 → green
    assert embed['color'] == 0x2ecc71


def test_build_quality_report_embed_insufficient_excluded_from_clean_rate():
    """INSUFFICIENT_DATA rows must not dilute the clean rate denominator."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 2, tzinfo=timezone.utc)
    counts = {'CLEAN_HIT': 3, 'MIXED': 0, 'NOISE': 1, 'WRONG_DIRECTION': 0,
              'INSUFFICIENT_DATA': 96}
    embed = build_quality_report_embed(start, end, 'rolling', 100, 100, counts)
    # decided = 3+0+1+0 = 4 (not 100) → clean rate 3/4 = 75%
    assert 'Clean rate **75.0%** (3/4 decided)' in embed['description']
    assert 'Insufficient data: **96**' in embed['description']


def test_build_quality_report_embed_color_thresholds():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 2, tzinfo=timezone.utc)
    # 40% clean → yellow (>=30, <50)
    yellow = build_quality_report_embed(
        start, end, 'rolling', 10, 10,
        {'CLEAN_HIT': 4, 'NOISE': 6})
    assert yellow['color'] == 0xf1c40f
    # 10% clean → red (<30)
    red = build_quality_report_embed(
        start, end, 'rolling', 10, 10,
        {'CLEAN_HIT': 1, 'NOISE': 9})
    assert red['color'] == 0xe74c3c


def test_build_quality_report_embed_zero_decided_no_div_by_zero():
    """All-insufficient batch — clean rate is 0%, must not raise."""
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 2, tzinfo=timezone.utc)
    embed = build_quality_report_embed(
        start, end, 'rolling', 5, 5, {'INSUFFICIENT_DATA': 5})
    assert 'Clean rate **0.0%** (0/0 decided)' in embed['description']


# ── #1166: score every session the writer adds, and say when one is left ──
#
# The nightly report and its writer (historical-signals-watchlist) both fired
# at 01:00 ET Tue-Sat, so the report read historical_signals before the
# writer had inserted the session it was about to add. The 2-day window
# picked a Mon-Thu session up the next night; Friday's, written by the
# Saturday run, fell out of Tuesday's window and was never scored. These pin
# the three halves of the fix: a heal window that selects unscored rows the
# regular window no longer covers, one source query and one coverage query
# however many sessions it heals, and a coverage check that fails the run
# when a row it selected is still unscored.

import scripts.signal_quality_report as sqr  # noqa: E402

# A Tuesday 01:30 ET nightly run (05:30 UTC under EDT), as scheduled.
_TUE = datetime(2026, 9, 29, 5, 30, tzinfo=timezone.utc)


def _nightly_args(*extra: str):
    return parse_args(["--mode", "historical", "--lookback-days", "2", *extra])


def test_parse_args_accepts_heal_days():
    assert _nightly_args("--heal-days", "7").heal_days == 7
    assert _nightly_args().heal_days is None


def test_resolve_heal_start_reaches_back_before_the_window():
    start, end = _TUE - timedelta(days=2), _TUE
    assert sqr._resolve_heal_start(_nightly_args("--heal-days", "7"), start, end) \
        == _TUE - timedelta(days=7)


def test_resolve_heal_start_is_none_without_the_flag():
    assert sqr._resolve_heal_start(_nightly_args(), _TUE - timedelta(days=2), _TUE) is None


def test_resolve_heal_start_never_starts_inside_the_window():
    # --heal-days shorter than the window adds nothing before it; the coverage
    # check still covers the whole window.
    start, end = _TUE - timedelta(days=2), _TUE
    assert sqr._resolve_heal_start(_nightly_args("--heal-days", "1"), start, end) == start


def test_resolve_heal_start_refuses_rolling_mode():
    args = parse_args(["--mode", "rolling", "--heal-days", "7"])
    with pytest.raises(ValueError, match="heal-days"):
        sqr._resolve_heal_start(args, _TUE - timedelta(hours=4), _TUE)


def test_resolve_heal_start_refuses_a_non_positive_count():
    with pytest.raises(ValueError, match="heal-days"):
        sqr._resolve_heal_start(_nightly_args("--heal-days", "0"),
                                _TUE - timedelta(days=2), _TUE)


def test_tuesdays_run_heals_fridays_session():
    """The case #1166 is about: Friday 2026-09-25's signals, written by the
    Saturday 01:00 ET writer after the Saturday report had read. Tuesday's
    2-day window starts on Sunday, so only the heal window reaches them."""
    args = _nightly_args("--heal-days", "7")
    start, end = _TUE - timedelta(days=2), _TUE
    heal_start = sqr._resolve_heal_start(args, start, end)
    for friday_bar in (datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc),
                       datetime(2026, 9, 25, 19, 59, tzinfo=timezone.utc)):
        assert not (start <= friday_bar < end)       # the window alone misses it
        assert heal_start <= friday_bar < start      # the heal range selects it


def _keys(*rows):
    return pd.DataFrame([{"ticker": t, "entry_time": pd.Timestamp(e, tz="UTC"),
                          "strategy": s} for t, e, s in rows])


def test_coverage_gaps_splits_missed_from_deferred():
    """Missed: a row this run selected and still did not score (a bug, or a
    ticker with no intraday bars). Deferred: a row the writer inserted after
    this run read, which the next run's heal window picks up."""
    selected = _keys(("SPY", "2026-09-25 14:00", "momentum"),
                     ("QQQ", "2026-09-25 14:00", "momentum"))
    unscored = _keys(("QQQ", "2026-09-25 14:00", "momentum"),
                     ("IWM", "2026-09-28 15:00", "momentum"))
    missed, deferred = sqr.coverage_gaps(unscored, selected)
    assert list(missed["ticker"]) == ["QQQ"]
    assert list(deferred["ticker"]) == ["IWM"]


def test_coverage_gaps_keys_on_strategy_too():
    selected = _keys(("SPY", "2026-09-25 14:00", "momentum"))
    unscored = _keys(("SPY", "2026-09-25 14:00", "mean_reversion"))
    missed, deferred = sqr.coverage_gaps(unscored, selected)
    assert missed.empty
    assert list(deferred["strategy"]) == ["mean_reversion"]


def test_coverage_gaps_empty_when_everything_scored():
    missed, deferred = sqr.coverage_gaps(
        pd.DataFrame(columns=["ticker", "entry_time", "strategy"]),
        _keys(("SPY", "2026-09-25 14:00", "momentum")))
    assert missed.empty and deferred.empty


def _run_main(argv, *, src, unscored, intraday):
    """main() with every I/O boundary mocked; returns (rc, source_calls,
    coverage_calls)."""
    source_calls: list[dict] = []
    coverage_calls: list[dict] = []

    def _source(_engine, start, end, **kw):
        source_calls.append({"start": start, "end": end, **kw})
        return src

    def _unscored(_engine, start, end, **kw):
        coverage_calls.append({"start": start, "end": end, **kw})
        return unscored

    with patch("gcp.database.get_engine", return_value=object()), \
         patch("scripts.signal_quality_report.fetch_source_rows", side_effect=_source), \
         patch("scripts.signal_quality_report.find_unscored_rows", side_effect=_unscored,
               create=True), \
         patch("scripts.signal_quality_report.fetch_intraday_window",
               side_effect=lambda _e, t, s, e: intraday.get(t, pd.DataFrame())), \
         patch("scripts.signal_quality_report.upsert_signal_metrics",
               side_effect=lambda _e, rows: len(rows)):
        rc = main(argv)
    return rc, source_calls, coverage_calls


_NIGHTLY = ["--mode", "historical", "--lookback-days", "2", "--heal-days", "7",
            "--skip-freshness-check"]


def test_main_heal_makes_one_source_query_and_one_coverage_query():
    """I/O shape: healing a week costs the same two round trips as healing a
    day. The heal rows arrive in the one source query, not per session."""
    base = pd.Timestamp("2026-09-25 14:30:00", tz="UTC")
    src = pd.concat([_three_signals_for_ticker("SPY", base),
                     _three_signals_for_ticker("QQQ", base + timedelta(days=3))],
                    ignore_index=True)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=6000)
    rc, source_calls, coverage_calls = _run_main(
        _NIGHTLY, src=src, unscored=pd.DataFrame(columns=["ticker", "entry_time", "strategy"]),
        intraday={"SPY": cache, "QQQ": cache})
    assert rc == 0
    assert len(source_calls) == 1 and len(coverage_calls) == 1
    heal_start = source_calls[0]["heal_start"]
    assert heal_start is not None
    assert source_calls[0]["end"] - heal_start == timedelta(days=7)
    # the coverage check covers the heal range and the window together
    assert coverage_calls[0]["start"] == heal_start
    assert coverage_calls[0]["end"] == source_calls[0]["end"]


def test_main_heal_fails_when_a_selected_row_is_still_unscored():
    """A row the run selected and could not score (here: no intraday bars
    for its ticker) is a silent gap unless the run says so. It exits 1, which
    the failure notifier turns into an issue."""
    base = pd.Timestamp("2026-09-25 14:30:00", tz="UTC")
    src = _three_signals_for_ticker("WEIRD", base)
    rc, _, _ = _run_main(_NIGHTLY, src=src, unscored=src[["ticker", "entry_time", "strategy"]],
                         intraday={})
    assert rc == 1


def test_main_heal_defers_rows_the_writer_added_during_the_run():
    """Rows inserted after the source query are not this run's failure: the
    next run's heal window selects them. Exit 0."""
    base = pd.Timestamp("2026-09-28 14:30:00", tz="UTC")
    src = _three_signals_for_ticker("SPY", base)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)
    late = _keys(("IWM", "2026-09-28 19:00", "momentum"))
    rc, _, coverage_calls = _run_main(_NIGHTLY, src=src, unscored=late,
                                      intraday={"SPY": cache})
    assert rc == 0
    assert len(coverage_calls) == 1


def test_main_dry_run_skips_the_coverage_check():
    base = pd.Timestamp("2026-09-28 14:30:00", tz="UTC")
    src = _three_signals_for_ticker("SPY", base)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)
    rc, _, coverage_calls = _run_main(_NIGHTLY + ["--dry-run"], src=src,
                                      unscored=src[["ticker", "entry_time", "strategy"]],
                                      intraday={"SPY": cache})
    assert rc == 0
    assert coverage_calls == []


def test_main_without_heal_days_runs_no_coverage_check():
    """Backfills and manual windows keep today's behaviour."""
    base = pd.Timestamp("2026-09-28 14:30:00", tz="UTC")
    src = _three_signals_for_ticker("SPY", base)
    cache = _make_synthetic_intraday(base - timedelta(minutes=120), bars=600)
    rc, source_calls, coverage_calls = _run_main(
        ["--mode", "historical", "--start", "2026-09-28", "--end", "2026-09-29",
         "--skip-freshness-check"],
        src=src, unscored=src[["ticker", "entry_time", "strategy"]], intraday={"SPY": cache})
    assert rc == 0
    assert source_calls[0].get("heal_start") is None
    assert coverage_calls == []


def test_main_heal_days_in_rolling_mode_returns_2():
    with patch("gcp.database.get_engine", return_value=object()):
        assert main(["--mode", "rolling", "--heal-days", "7"]) == 2


def test_build_quality_report_embed_reports_healed_rows():
    start = datetime(2026, 9, 27, 5, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 29, 5, 30, tzinfo=timezone.utc)
    embed = build_quality_report_embed(start, end, "historical", 10, 10,
                                       {"CLEAN_HIT": 5, "NOISE": 5}, healed=4)
    assert "4" in embed["description"] and "before the window" in embed["description"]
    plain = build_quality_report_embed(start, end, "historical", 10, 10,
                                       {"CLEAN_HIT": 5, "NOISE": 5})
    assert "before the window" not in plain["description"]


def _nightly_schedulers():
    from scripts.maintenance.doc_inventory import deploy_schedulers
    return {s["name"]: s for s in deploy_schedulers()}


def test_nightly_report_is_scheduled_after_its_writer_and_heals():
    """The schedule half of #1166, read from gcp/deploy.sh with the parser the
    doc inventory uses. Same days, a later clock time than the writer, and
    the heal window in its args."""
    sched = _nightly_schedulers()
    report = sched["signal-quality-report-nightly"]
    writer = sched["historical-signals-watchlist-daily"]
    r_min, r_hour, *_, r_dow = report["cron"].split()
    w_min, w_hour, *_, w_dow = writer["cron"].split()
    assert r_dow == w_dow
    assert (int(r_hour), int(r_min)) > (int(w_hour), int(w_min))
    assert "--heal-days=" in report["args"]
    alarm = sched["signal-quality-alarm-daily"]
    a_min, a_hour, *_ = alarm["cron"].split()
    assert (int(a_hour), int(a_min)) > (int(r_hour), int(r_min))


def test_the_nightly_scheduler_is_updated_not_only_created():
    """Codex on #1186: `_schedule_with_args` swallows "already exists", so
    `deploy.sh schedulers` or `all` left the live entry at the old cron and
    args. The verified helper updates, reads back, and counts a failure."""
    assert _nightly_schedulers()["signal-quality-report-nightly"]["helper"] \
        == "_schedule_with_args_verified"


def test_the_nightly_heal_reaches_a_new_tickers_bootstrap():
    """Codex on #1186: the writer bootstraps a (ticker, strategy) with no rows
    from BOOTSTRAP_DAYS back. A 7-day heal left the rest of that month written
    and never scored. The window must reach the whole bootstrap, which starts
    BOOTSTRAP_DAYS - 1 days before the writer's run (its end is exclusive, a
    day ahead), from a report run half an hour later."""
    import re
    from scripts.run_historical_signals import BOOTSTRAP_DAYS
    args = _nightly_schedulers()["signal-quality-report-nightly"]["args"]
    heal = int(re.search(r"--heal-days=(\d+)", args).group(1))
    assert heal >= BOOTSTRAP_DAYS, (heal, BOOTSTRAP_DAYS)
    # And in the report's own terms: the oldest bootstrap row is selected.
    run = _TUE
    oldest_bootstrap = run + timedelta(days=1) - timedelta(days=BOOTSTRAP_DAYS)
    start, end = run - timedelta(days=2), run
    heal_start = sqr._resolve_heal_start(
        _nightly_args("--heal-days", str(heal)), start, end)
    assert heal_start <= oldest_bootstrap < start
