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

_REPO = Path(__file__).resolve().parents[1]
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
    src = {
        "ticker":         "SPY",
        "entry_time":     entry,
        "strategy":       "momentum",
        "trade_type":     "CALL",
        "entry_price":    100.0,
        "return_5min":    0.0006,    # NOISE
        "return_15min":   0.0040,    # MIXED
        "return_30min":   0.0070,    # CLEAN_HIT
        "return_60min":   0.0150,    # CLEAN_HIT
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
    assert m.atr_5m_pct == pytest.approx(0.02, rel=1e-3)
    # mfe_60m_atrs = 0.015 / 0.02 = 0.75
    assert m.mfe_60m_atrs == pytest.approx(0.75, rel=1e-3)
    assert m.status == "final"  # historical mode


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
