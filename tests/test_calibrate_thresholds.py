"""Unit tests for scripts/calibrate_thresholds.py.

These tests are hermetic — they don't hit Cloud SQL. They:

1. Feed synthetic 1-min bars with known statistics into the helpers
   (compute_atr_pct, compute_rsi, compute_rvol, resample_to_tf) and
   assert the outputs match expected values.
2. Run the full calibrate_ticker() pipeline on synthetic data and
   verify the produced row has every required column populated, with
   thresholds derived correctly from ATR.

This catches regressions in the calibration math BEFORE the quarterly
Cloud Run Job runs in production.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from scripts.calibrate_thresholds import (
    CLEAN_ATR_MULT,
    NOISE_ATR_MULT,
    TIMEFRAMES_MIN,
    WRONG_ATR_MULT,
    calibrate_ticker,
    compute_atr_pct,
    compute_rsi,
    compute_rvol,
    resample_to_tf,
)


# ── Synthetic-bar fixtures ──────────────────────────────────────────────

def synthetic_bars(
    n: int = 1500,
    base_price: float = 100.0,
    daily_vol_pct: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate n synthetic 1-min OHLCV bars with controlled volatility."""
    rng = np.random.default_rng(seed)
    # Random-walk close
    returns = rng.normal(0, daily_vol_pct / 100 / np.sqrt(390), size=n)
    closes = base_price * np.cumprod(1 + returns)
    # Highs and lows wrapped around close with modest noise
    spreads = np.abs(rng.normal(0, daily_vol_pct / 100 * 0.3, size=n)) * closes
    highs = closes + spreads * 0.6
    lows  = closes - spreads * 0.4
    opens = np.roll(closes, 1)
    opens[0] = base_price
    volumes = rng.integers(1000, 10000, size=n).astype(np.int64)

    start = datetime(2026, 4, 1, 13, 30, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame({
        "ts": ts, "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


# ── compute_atr_pct ─────────────────────────────────────────────────────

def test_atr_pct_returns_empty_when_too_few_bars():
    bars = synthetic_bars(n=10)
    out = compute_atr_pct(bars, period=14)
    assert out.empty


def test_atr_pct_warmup_observed():
    """The first several bars should be NaN during the rolling-window
    warmup; well past warmup, values should be valid."""
    bars = synthetic_bars(n=200)
    out = compute_atr_pct(bars, period=14)
    # First few bars NaN (warmup of rolling-14 + the c.shift(1) NaN)
    assert out.iloc[:13].isna().all(), "first 13 bars should be NaN during warmup"
    # Well past warmup, plenty of valid values
    assert out.iloc[20:].notna().sum() > 100


def test_atr_pct_scales_with_volatility():
    """High-vol bars should produce a higher ATR than low-vol bars."""
    low_vol  = synthetic_bars(n=500, daily_vol_pct=0.3)
    high_vol = synthetic_bars(n=500, daily_vol_pct=2.0)
    atr_low  = float(compute_atr_pct(low_vol).dropna().median())
    atr_high = float(compute_atr_pct(high_vol).dropna().median())
    assert atr_high > atr_low * 2, (
        f"high-vol ATR ({atr_high:.4f}%) should be at least 2× low-vol ATR ({atr_low:.4f}%)"
    )


# ── compute_rsi ─────────────────────────────────────────────────────────

def test_rsi_returns_in_range():
    bars = synthetic_bars(n=500)
    rsi = compute_rsi(bars["close"]).dropna()
    assert rsi.min() >= 0
    assert rsi.max() <= 100


def test_rsi_for_strongly_rising_close_approaches_100():
    """A strongly-rising series (with tiny noise so loss > 0) should
    push Wilder RSI very high. Threshold >80; real-market signals
    rarely exceed 90 even on momentum rallies."""
    rng = np.random.default_rng(0)
    base = np.linspace(100, 200, 500)
    noise = rng.normal(0, 0.05, size=500)  # tiny chop so loss != 0
    closes = pd.Series(base + noise)
    rsi = compute_rsi(closes).dropna()
    assert len(rsi) > 0, "RSI should have non-NaN values on a noisy series"
    assert rsi.iloc[-1] > 80, (
        f"RSI on strongly-rising series should be >80, got {rsi.iloc[-1]:.2f}"
    )


def test_rsi_for_strongly_falling_close_approaches_0():
    """Mirror of the rising test."""
    rng = np.random.default_rng(1)
    base = np.linspace(200, 100, 500)
    noise = rng.normal(0, 0.05, size=500)
    closes = pd.Series(base + noise)
    rsi = compute_rsi(closes).dropna()
    assert len(rsi) > 0
    assert rsi.iloc[-1] < 20, (
        f"RSI on strongly-falling series should be <20, got {rsi.iloc[-1]:.2f}"
    )


# ── compute_rvol ────────────────────────────────────────────────────────

def test_rvol_centered_around_1_for_uniform_volume():
    """Volume drawn from the same distribution should have RVOL median ≈ 1."""
    rng = np.random.default_rng(0)
    vol = pd.Series(rng.integers(1000, 10000, size=500))
    rvol = compute_rvol(vol, period=20).dropna()
    assert 0.85 < float(rvol.median()) < 1.15, (
        f"RVOL median should be near 1.0 for stationary volume, got {rvol.median():.3f}"
    )


# ── resample_to_tf ─────────────────────────────────────────────────────

def test_resample_5m_groups_5_bars_into_1():
    bars = synthetic_bars(n=100)  # 100 1-min bars
    out = resample_to_tf(bars, 5)
    # ~100/5 = 20 5-min bars (give or take edge effects)
    assert 18 <= len(out) <= 22, f"5-min resample of 100 1-min bars should produce ~20 rows, got {len(out)}"
    # OHLC integrity
    assert (out["high"] >= out["low"]).all()
    assert (out["high"] >= out["close"]).all()
    assert (out["high"] >= out["open"]).all()


def test_resample_60m_volume_is_sum_not_average():
    """Resampled total volume across all hourly bars should equal
    the total volume across all 1-min bars (volume is conserved under
    sum-aggregation)."""
    bars = synthetic_bars(n=120)
    out = resample_to_tf(bars, 60)
    expected_total = bars["volume"].sum()
    actual_total = out["volume"].sum()
    # Edge bars at boundaries may shift slightly under closed='right' so
    # check totals match within a 5% tolerance (which would catch a
    # mean vs sum bug — that'd be a 60× difference, not 5%).
    assert abs(actual_total - expected_total) / expected_total < 0.05, (
        f"resampled volume total ({actual_total}) should be ~equal to "
        f"raw volume total ({expected_total}); large diff = mean instead of sum"
    )
    # And: sum-aggregation produces values 30-100× larger than mean would
    if len(out) > 0:
        assert out["volume"].iloc[0] > bars["volume"].mean() * 5, (
            "resampled bar volume should be much larger than 1-min average"
        )


# ── calibrate_ticker (end-to-end on synthetic data) ─────────────────────

def test_calibrate_ticker_produces_required_columns():
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    required = {"ticker", "calibration_date", "lookback_days", "n_bars_used",
                "earliest_bar_date", "latest_bar_date",
                "threshold_clean", "threshold_wrong", "threshold_noise",
                "rvol_min", "rvol_max", "atr_expansion_x",
                "rvol_p25", "rvol_p50", "rvol_p75", "rvol_p95",
                "rsi_p10", "rsi_p25", "rsi_p50", "rsi_p75", "rsi_p90"}
    for tf in TIMEFRAMES_MIN:
        required.add(f"atr_{tf}_median")
    missing = required - set(cal.keys())
    assert not missing, f"calibrate_ticker missing required keys: {missing}"


def test_calibrate_ticker_thresholds_are_atr_multiplied():
    """clean threshold per timeframe must equal ATR × CLEAN_ATR_MULT."""
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    clean = json.loads(cal["threshold_clean"])
    wrong = json.loads(cal["threshold_wrong"])
    noise = json.loads(cal["threshold_noise"])

    for tf in clean:
        atr = cal[f"atr_{tf}_median"]
        assert atr is not None
        # Clean threshold = ATR × CLEAN_ATR_MULT
        assert clean[tf] == pytest.approx(atr * CLEAN_ATR_MULT, abs=1e-3), (
            f"{tf} clean threshold {clean[tf]} should equal atr_{tf}={atr} × {CLEAN_ATR_MULT}"
        )
        # Wrong threshold is signed negative
        assert wrong[tf] < 0
        assert wrong[tf] == pytest.approx(-atr * WRONG_ATR_MULT, abs=1e-3)
        # Noise threshold (smaller than clean)
        assert noise[tf] == pytest.approx(atr * NOISE_ATR_MULT, abs=1e-3)
        assert noise[tf] < clean[tf]


def test_calibrate_ticker_rvol_band_is_subset_of_distribution():
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    assert cal["rvol_min"] >= cal["rvol_p25"] - 0.01, (
        f"rvol_min ({cal['rvol_min']}) should be near or below P25 ({cal['rvol_p25']})"
    )
    assert cal["rvol_max"] <= cal["rvol_p95"] + 0.01, (
        f"rvol_max ({cal['rvol_max']}) should be near or below P95 ({cal['rvol_p95']})"
    )
    assert cal["rvol_min"] < cal["rvol_max"]


def test_high_vol_ticker_has_higher_thresholds_than_low_vol_ticker():
    """A volatile ticker should get LOOSER thresholds than a calm one
    — that's the whole point of per-ticker calibration."""
    low_vol  = synthetic_bars(n=2000, daily_vol_pct=0.3, seed=1)
    high_vol = synthetic_bars(n=2000, daily_vol_pct=2.0, seed=2)
    cal_low  = calibrate_ticker("LOW",  low_vol,  60)
    cal_high = calibrate_ticker("HIGH", high_vol, 60)

    clean_low  = json.loads(cal_low["threshold_clean"])
    clean_high = json.loads(cal_high["threshold_clean"])
    for tf in clean_low:
        assert clean_high[tf] > clean_low[tf] * 2, (
            f"{tf}: high-vol ticker's clean threshold ({clean_high[tf]}) should be "
            f"≥ 2× low-vol ticker's ({clean_low[tf]}) — proves calibration is per-ticker"
        )


def test_calibrate_ticker_missing_long_tf_yields_none_not_zero():
    """Rule 3.7 invariant: a timeframe with too few resampled bars to
    compute ATR must produce atr_<tf>_median == None (missing), NOT a
    silent 0.0 that downstream code can't distinguish from a real low-vol
    reading. With only ~120 1-min bars the 240m frame resamples to <15
    rows, so its ATR can't be computed; the short frames still can.
    Asserts on the REAL calibrate_ticker output."""
    bars = synthetic_bars(n=120)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    # 240m frame: 120 1-min bars → 1 row → ATR(period=14) impossible → None
    assert cal["atr_240m_median"] is None, (
        "insufficient long-timeframe data must be None, not a fabricated 0"
    )
    # That missing frame must NOT appear in the composed thresholds — the
    # production loop `continue`s past it rather than writing a 0 threshold.
    clean = json.loads(cal["threshold_clean"])
    assert "240m" not in clean, "missing-ATR timeframe must be omitted, not 0"
    # Short frames with enough bars still compute a real, positive ATR.
    assert cal["atr_5m_median"] is not None and cal["atr_5m_median"] > 0
    assert clean["5m"] == pytest.approx(
        cal["atr_5m_median"] * CLEAN_ATR_MULT, abs=1e-3)


def test_calibrate_ticker_rvol_distribution_is_monotone_nondecreasing():
    """The four RVOL percentiles emitted by the real pipeline must be
    monotonically non-decreasing (P25 ≤ P50 ≤ P75 ≤ P95) and centered
    near 1.0 for the synthetic stationary-volume bars. Invariant check on
    real computed output — no hand-typed expected numbers."""
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)

    p25, p50, p75, p95 = (
        cal["rvol_p25"], cal["rvol_p50"], cal["rvol_p75"], cal["rvol_p95"])
    assert p25 <= p50 <= p75 <= p95, (
        f"RVOL percentiles must be monotone non-decreasing, "
        f"got {p25}, {p50}, {p75}, {p95}")
    # Stationary uniform-ish volume → median RVOL near 1.0.
    assert 0.85 < p50 < 1.15
    # RSI percentiles likewise monotone non-decreasing.
    rsi = [cal["rsi_p10"], cal["rsi_p25"], cal["rsi_p50"],
           cal["rsi_p75"], cal["rsi_p90"]]
    assert rsi == sorted(rsi), f"RSI percentiles must be sorted, got {rsi}"
    assert all(0 <= v <= 100 for v in rsi), "RSI percentiles must be in [0,100]"


def test_calibrate_ticker_returns_empty_for_empty_bars():
    cal = calibrate_ticker("EMPTY", pd.DataFrame(columns=["ts","open","high","low","close","volume"]), 60)
    assert cal == {}, "empty bars should produce empty calibration dict (skip, not crash)"


# ── --as-of flag (added 2026-05-10 for #250 backfill) ─────────────────────

def test_calibrate_ticker_with_as_of_overrides_calibration_date():
    """When `as_of=date(2026, 4, 1)` is passed, the output row's
    calibration_date is the passed date, not date.today()."""
    from datetime import date as _date
    bars = synthetic_bars(n=2000)
    target = _date(2026, 4, 1)
    cal = calibrate_ticker("TEST", bars, lookback_days=60, as_of=target)
    assert cal["calibration_date"] == target


def test_calibrate_ticker_without_as_of_uses_today():
    """Default (no as_of) is today — preserves existing live cadence."""
    from datetime import date as _date
    bars = synthetic_bars(n=2000)
    cal = calibrate_ticker("TEST", bars, lookback_days=60)
    assert cal["calibration_date"] == _date.today()


def test_parse_as_of_accepts_valid_iso_date():
    from datetime import date as _date
    from scripts.calibrate_thresholds import _parse_as_of
    assert _parse_as_of("2025-10-01") == _date(2025, 10, 1)


def test_parse_as_of_returns_none_when_unset():
    from scripts.calibrate_thresholds import _parse_as_of
    assert _parse_as_of(None) is None
    assert _parse_as_of("") is None


def test_parse_as_of_rejects_invalid_string():
    from scripts.calibrate_thresholds import _parse_as_of
    with pytest.raises(SystemExit, match="not a valid YYYY-MM-DD"):
        _parse_as_of("not-a-date")


def test_parse_as_of_rejects_future_date():
    """Future dates would calibrate against bars that don't exist —
    the script must refuse so the backfill can't accidentally
    write a row with calibration_date > today."""
    from datetime import date as _date, timedelta as _td
    from scripts.calibrate_thresholds import _parse_as_of
    future = (_date.today() + _td(days=7)).isoformat()
    with pytest.raises(SystemExit, match="in the future"):
        _parse_as_of(future)


def test_parse_as_of_accepts_today_boundary():
    """Today is allowed (cadence parity with no-flag run)."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import _parse_as_of
    today_str = _date.today().isoformat()
    assert _parse_as_of(today_str) == _date.today()


# ── #250 Drift guard ─────────────────────────────────────────────────────

def _drift_prior_df(values_per_col: dict) -> pd.DataFrame:
    """Build a synthetic 4-row prior-history DataFrame for check_drift().
    `values_per_col` maps column → list of 4 prior values."""
    from datetime import date as _date
    rows = []
    for i, dt in enumerate(["2025-04-01", "2025-07-01", "2025-10-01", "2026-01-01"]):
        row = {"calibration_date": _date.fromisoformat(dt)}
        for col, vals in values_per_col.items():
            row[col] = vals[i]
        rows.append(row)
    return pd.DataFrame(rows)


def _stub_eng_returning(prior_df: pd.DataFrame, monkeypatch):
    """Patch pd.read_sql so check_drift's SQL pull returns prior_df.
    The eng object is opaque — only its identity matters for the patch."""
    monkeypatch.setattr(
        "pandas.read_sql",
        lambda sql, eng, params: prior_df.copy(),
    )


def test_drift_no_prior_rows_passes_through(monkeypatch):
    """0 prior rows → pass-through, no flag, no refuse."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    _stub_eng_returning(pd.DataFrame(columns=["calibration_date", "atr_60m_median"]), monkeypatch)
    new_row = {"calibration_date": _date(2026, 4, 1), "atr_60m_median": 1.0}
    drift, refuse, msgs = check_drift("SPY", new_row, eng=None)
    assert drift is False
    assert refuse is False


def test_drift_below_2_sigma_no_flag(monkeypatch):
    """4 prior rows clustered tightly + new row within 2σ → no flag."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    # Prior values 1.0/1.0/1.0/1.0 → mean=1, sd=0. Edge case: handled
    # separately — use slightly varied values.
    prior = _drift_prior_df({"atr_60m_median": [1.00, 1.02, 0.98, 1.01]})
    _stub_eng_returning(prior, monkeypatch)
    # mean ≈ 1.0025, sd ≈ 0.017, 2σ band ≈ ±0.034
    new_row = {"calibration_date": _date(2026, 4, 15), "atr_60m_median": 1.015}
    drift, refuse, _ = check_drift("SPY", new_row, eng=None)
    assert drift is False, "1.015 vs mean 1.0025 with sd 0.017 is well within 2σ"
    assert refuse is False


def test_drift_above_2_sigma_flags_no_refuse(monkeypatch):
    """4 prior rows + new row at ~2.5σ → drift_flagged=True, refuse=False."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    prior = _drift_prior_df({"atr_60m_median": [1.00, 1.02, 0.98, 1.01]})
    _stub_eng_returning(prior, monkeypatch)
    # Push to ~2.5σ above mean: mean ≈ 1.0025, sd ≈ 0.017, so 1.044 ≈ 2.4σ
    new_row = {"calibration_date": _date(2026, 4, 15), "atr_60m_median": 1.05}
    drift, refuse, msgs = check_drift("SPY", new_row, eng=None)
    assert drift is True
    assert refuse is False, "2-3σ should flag but not refuse"
    assert any("DRIFT" in m for m in msgs)


def test_drift_above_3_sigma_refuses(monkeypatch):
    """4 prior rows + new row at ~5σ → refuse=True (caller respects --force)."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    prior = _drift_prior_df({"atr_60m_median": [1.00, 1.02, 0.98, 1.01]})
    _stub_eng_returning(prior, monkeypatch)
    # 5σ — clearly past 3σ refusal threshold
    new_row = {"calibration_date": _date(2026, 4, 15), "atr_60m_median": 2.0}
    drift, refuse, msgs = check_drift("SPY", new_row, eng=None)
    assert drift is True
    assert refuse is True
    assert any("REFUSE" in m for m in msgs)


def test_drift_flat_history_any_change_flags(monkeypatch):
    """Prior values all identical (sd=0) — any change should flag."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    prior = _drift_prior_df({"atr_60m_median": [1.0, 1.0, 1.0, 1.0]})
    _stub_eng_returning(prior, monkeypatch)
    new_row = {"calibration_date": _date(2026, 4, 15), "atr_60m_median": 1.001}
    drift, refuse, msgs = check_drift("SPY", new_row, eng=None)
    assert drift is True
    assert refuse is False  # flat-history flag is warn-level, not refuse
    assert any("flat" in m.lower() for m in msgs)


def test_drift_skips_new_row_with_none_value(monkeypatch):
    """A NULL new value isn't compared — moves on to other columns."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    prior = _drift_prior_df({
        "atr_60m_median": [1.0, 1.02, 0.98, 1.01],
        "rsi_p50":        [50.0, 51.0, 49.0, 50.5],
    })
    _stub_eng_returning(prior, monkeypatch)
    new_row = {
        "calibration_date": _date(2026, 4, 15),
        "atr_60m_median": None,    # skip — no comparison
        "rsi_p50": 50.2,           # within 2σ
    }
    drift, refuse, _ = check_drift("SPY", new_row, eng=None)
    assert drift is False
    assert refuse is False


def test_drift_min_prior_rows_threshold(monkeypatch):
    """Only 2 prior rows → can't compute drift, returns False/False."""
    from datetime import date as _date
    from scripts.calibrate_thresholds import check_drift
    prior = pd.DataFrame([
        {"calibration_date": _date(2025, 10, 1), "atr_60m_median": 1.0},
        {"calibration_date": _date(2026, 1, 1), "atr_60m_median": 1.0},
    ])
    _stub_eng_returning(prior, monkeypatch)
    new_row = {"calibration_date": _date(2026, 4, 1), "atr_60m_median": 5.0}
    drift, refuse, msgs = check_drift("SPY", new_row, eng=None)
    assert drift is False, "fewer than 3 prior rows should pass-through"
    assert refuse is False
    assert any("skipping drift check" in m for m in msgs)
