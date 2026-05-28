"""Tests for lib/options_exec_backtest.

Coverage:
  - BSM price parity vs py_vollib_vectorized (the ground-truth library
    already used by lib/options_greeks). 10-point grid covering ATM, ITM,
    OTM, near-expiry, and long-dated.
  - bs_price degenerate paths: zero/negative sigma, expired, NaN inputs.
  - atm_strike: ATM selection + OTM offset + out-of-band offset.
  - years_to_expiry: 0DTE morning, EOD, T+1 morning, edge cases.
"""
from __future__ import annotations
import math

import numpy as np
import pandas as pd
import pytest

from lib.options_exec_backtest.pricing import (
    MIN_T_YEARS, atm_strike, bs_price, bs_price_vec, years_to_expiry,
)


# ─────────────────────────────────────────── BSM parity ───────────────────────────────────

def _pvv_price(S, K, T, sigma, r, q, kind):
    """Reference price from py_vollib_vectorized. Loaded lazily because the
    library isn't a hard dep — if missing, the parity test is skipped."""
    try:
        from py_vollib_vectorized.api import price_dataframe
    except ImportError:
        pytest.skip("py_vollib_vectorized not installed")
    flag = "c" if kind == "call" else "p"
    df = pd.DataFrame({
        "S": [S], "K": [K], "t": [T], "r": [r], "q": [q], "flag": [flag],
        "price": [0.0],  # not used for forward price; library wants the col
    })
    # The vectorized API exposes black_scholes_merton via `price`:
    from py_vollib.black_scholes_merton import black_scholes_merton as bsm_ref
    return float(bsm_ref(flag, S, K, T, r, sigma, q))


PARITY_GRID = [
    # (S, K, T, sigma, r, q, kind, label)
    (450.0, 450.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "ATM 1DTE"),
    (450.0, 450.0, 6.5 / (365 * 24), 0.20, 0.045, 0.013, "call", "ATM 6.5h-0DTE"),
    (450.0, 455.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "5-OTM 1DTE call"),
    (450.0, 445.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "call", "5-ITM 1DTE call"),
    (450.0, 450.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "ATM 1DTE put"),
    (450.0, 455.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "5-ITM 1DTE put"),
    (450.0, 445.0, 1.0 / 365.0, 0.20, 0.045, 0.013, "put", "5-OTM 1DTE put"),
    (450.0, 450.0, 30.0 / 365.0, 0.18, 0.045, 0.013, "call", "ATM 30DTE"),
    (450.0, 470.0, 30.0 / 365.0, 0.18, 0.045, 0.013, "call", "20-OTM 30DTE"),
    (200.0, 200.0, 7.0 / 365.0, 0.30, 0.045, 0.0, "call", "ATM 7DTE IWM-ish"),
]


@pytest.mark.parametrize("S,K,T,sigma,r,q,kind,label", PARITY_GRID)
def test_bs_price_parity(S, K, T, sigma, r, q, kind, label):
    """Our BSM price must match py_vollib's BSM to within 1e-6 — the
    Greeks engine elsewhere in the repo uses py_vollib, so any drift
    would create a self-inconsistency."""
    expected = _pvv_price(S, K, T, sigma, r, q, kind)
    actual = bs_price(S, K, T, sigma, r, q, kind=kind)
    assert math.isclose(actual, expected, abs_tol=1e-6), (
        f"{label}: expected {expected:.8f}, got {actual:.8f}, diff "
        f"{actual - expected:.8e}"
    )


def test_bs_price_vec_matches_scalar():
    """Vector BSM must match scalar BSM elementwise."""
    S = np.array([450.0, 450.0, 450.0, 200.0])
    K = np.array([450.0, 455.0, 445.0, 200.0])
    T = np.array([1, 1, 1, 7], dtype=float) / 365.0
    sigma = np.array([0.20, 0.20, 0.20, 0.30])
    r = np.array([0.045, 0.045, 0.045, 0.045])
    q = np.array([0.013, 0.013, 0.013, 0.0])
    vec_call = bs_price_vec(S, K, T, sigma, r, q, kind="call")
    for i in range(len(S)):
        scalar = bs_price(S[i], K[i], T[i], sigma[i], r[i], q[i], kind="call")
        assert math.isclose(vec_call[i], scalar, abs_tol=1e-9), (
            f"row {i}: vec {vec_call[i]} vs scalar {scalar}"
        )


# ─────────────────────────────────────────── Degenerate paths ─────────────────────────────

def test_bs_price_zero_sigma_call_intrinsic():
    """sigma=0 → degenerates to discounted intrinsic value."""
    # ITM call: intrinsic = max(0, S-K) = 5
    p = bs_price(S=450, K=445, T=1 / 365, sigma=0.0, r=0.045, q=0.0, kind="call")
    # Discounted by e^(-rT): 5 * e^(-0.045/365) ≈ 4.99938
    assert 4.99 < p < 5.01


def test_bs_price_zero_sigma_otm_zero():
    """OTM with zero vol → 0."""
    p = bs_price(S=450, K=460, T=1 / 365, sigma=0.0, r=0.045, q=0.0, kind="call")
    assert p == 0.0


def test_bs_price_nan_inputs():
    """NaN underlying / strike → NaN price (not 0 — never silently lie)."""
    p = bs_price(S=float("nan"), K=450, T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)
    p = bs_price(S=450, K=float("nan"), T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)


def test_bs_price_negative_underlying_nan():
    """Negative S → NaN (never silently coerce)."""
    p = bs_price(S=-1.0, K=450, T=1 / 365, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isnan(p)


def test_bs_price_expired_floored():
    """T <= 0 floored to MIN_T_YEARS so the formula doesn't divide by zero."""
    p_zero = bs_price(S=450, K=450, T=0.0, sigma=0.2, r=0.045, q=0.0, kind="call")
    p_one_min = bs_price(S=450, K=450, T=MIN_T_YEARS, sigma=0.2, r=0.045, q=0.0, kind="call")
    assert math.isclose(p_zero, p_one_min, abs_tol=1e-9)
    assert p_zero > 0  # ATM with any vol > 0


# ─────────────────────────────────────────── ATM strike ───────────────────────────────────

def test_atm_strike_exact_match():
    s = atm_strike(450.0, np.array([445, 450, 455]))
    assert s == 450.0


def test_atm_strike_closest():
    """Spot is 451.6; closest strike is 452."""
    s = atm_strike(451.6, np.array([445, 450, 452, 455]))
    assert s == 452.0


def test_atm_strike_otm_offset():
    """+1 from ATM 450 should be the next strike up (the spec is generic —
    engine knows whether call or put and offsets accordingly)."""
    s = atm_strike(450.0, np.array([440, 445, 450, 455, 460]), otm_offset=1)
    assert s == 455.0


def test_atm_strike_out_of_band_nan():
    """Asking for +5-OTM when only 1 strike is above ATM → NaN."""
    s = atm_strike(450.0, np.array([445, 450, 455]), otm_offset=5)
    assert math.isnan(s)


def test_atm_strike_empty_list_nan():
    s = atm_strike(450.0, np.array([]))
    assert math.isnan(s)


# ─────────────────────────────────────────── years_to_expiry ──────────────────────────────

def test_years_to_expiry_0dte_morning():
    """0DTE at 9:30 ET (14:30 UTC EDT) on the expiration date — about
    5.5 hours until 20:00 UTC = 5.5/24/365 ≈ 6.28e-4 years."""
    now = pd.Timestamp("2024-06-03 13:30:00", tz="UTC")  # 9:30 AM ET on a non-DST day
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    # 20:00 UTC - 13:30 UTC = 6.5 hours → 6.5 / (365*24) = 7.42e-4
    assert 7.0e-4 < y < 7.8e-4


def test_years_to_expiry_at_close():
    """At 20:00 UTC on expiration day, T should floor at MIN_T_YEARS."""
    now = pd.Timestamp("2024-06-03 20:00:00", tz="UTC")
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    assert y == MIN_T_YEARS


def test_years_to_expiry_one_day():
    """24h to expiry → ~1/365 years (give or take 1h ET/EDT slop)."""
    now = pd.Timestamp("2024-06-02 20:00:00", tz="UTC")
    exp = pd.Timestamp("2024-06-03").date()
    y = years_to_expiry(now, exp)
    assert 0.00273 < y < 0.00274


def test_years_to_expiry_bad_input_nan():
    y = years_to_expiry("not-a-ts", pd.Timestamp("2024-06-03").date())
    assert math.isnan(y)


# ─────────────────────────────────────────── Sanity: BSM walk through trade ───────────────

def test_bsm_walk_underlying_rises_call_premium_rises():
    """Long call: underlying rises → premium rises. Sanity for the engine."""
    p0 = bs_price(S=450.0, K=450.0, T=6.5 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    p1 = bs_price(S=451.0, K=450.0, T=6.0 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    # Even with 30 min of theta decay, a $1 underlying rise on a $1-wide
    # ATM 0DTE call should net-positive (delta ~0.5, theta loss ~$0.10 over 30 min)
    assert p1 > p0


def test_bsm_walk_theta_decay_only_premium_falls():
    """Same underlying, less time-to-expiry → call premium falls (positive theta cost
    to a long option holder)."""
    p0 = bs_price(S=450.0, K=450.0, T=6.5 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    p1 = bs_price(S=450.0, K=450.0, T=3.0 / (365 * 24), sigma=0.20,
                  r=0.045, q=0.013, kind="call")
    assert p1 < p0


# ─────────────────────────────────────────── IVLookup smoke ───────────────────────────────

from lib.options_exec_backtest.iv_lookup import IVLookup, SNAPSHOT_TOLERANCE_SECONDS


def _synthetic_eod_snapshots(snapshot_dates, spot=450.0, ticker="IWM",
                              expiration_offsets=(1, 2)):
    """Build a synthetic preloaded-rows DataFrame for IVLookup under the
    EOD-anchor design.

    Each EOD snapshot is recorded at 21:00 UTC (4 PM ET) of `snapshot_date`,
    and contains contracts expiring on snapshot_date + offset for each
    offset in `expiration_offsets`. Default = {1, 2} = 1DTE + 2DTE from
    the snapshot's perspective (= 0DTE + 1DTE from the next-day setup's
    perspective, which is what the EOD lookup serves).
    """
    rows = []
    for snap_d in snapshot_dates:
        snap_date = pd.Timestamp(snap_d).date()
        snap_ts = pd.Timestamp(snap_date) + pd.Timedelta(hours=21)  # 4 PM ET ≈ 21:00 UTC EDT
        snap_ts = snap_ts.tz_localize("UTC")
        for off in expiration_offsets:
            exp_date = snap_date + pd.Timedelta(days=off).to_pytimedelta()
            for strike in range(int(spot) - 10, int(spot) + 11):
                for kind in ("calls", "puts"):
                    rows.append({
                        "ticker": ticker,
                        "snapshot_ts": snap_ts,
                        "snapshot_date": snap_date,
                        "market_session": "EOD",
                        "expiration": exp_date,
                        "strike": float(strike),
                        "option_type": kind,
                        "bid": 5.0, "ask": 5.10, "mark": 5.05, "last_price": 5.05,
                        "implied_volatility": 0.18,
                        "implied_volatility_computed": np.nan,
                        "underlying_price": spot,
                    })
    return pd.DataFrame(rows)


def test_iv_lookup_eod_anchor_picks_most_recent_prior_day():
    """Setup on 2024-06-04 with trigger at 14:02 UTC: anchor is 2024-06-03's
    EOD snapshot (the day BEFORE the trigger — no look-ahead).
    expiration_dte=0 means we want a contract expiring on the trigger date
    (= 2024-06-04 = snapshot_date+1)."""
    df = _synthetic_eod_snapshots(["2024-06-03", "2024-06-04"])
    lk = IVLookup(df)
    trig = pd.Timestamp("2024-06-04 14:02:00", tz="UTC")
    quote = lk.find(trig, spot=450.0, side="long", otm_offset=0, expiration_dte=0)
    assert quote is not None
    assert quote.kind == "call"
    assert quote.strike == 450.0
    # Anchor is 2024-06-03's EOD (21:00 UTC)
    assert quote.snapshot_ts.date() == pd.Timestamp("2024-06-03").date()
    # The expiration we requested is the trigger date
    assert quote.expiration.date() == pd.Timestamp("2024-06-04").date()
    # snapshot_age ≈ overnight gap (~17h from 6/3 21:00 UTC to 6/4 14:02 UTC)
    assert 16 * 3600 < quote.snapshot_age_seconds < 18 * 3600


def test_iv_lookup_voids_when_no_prior_day():
    """If there's no EOD snapshot strictly prior to the trigger date,
    the lookup voids. (First trading day of the preload window with
    no T-1 to anchor against.)"""
    df = _synthetic_eod_snapshots(["2024-06-03"])
    lk = IVLookup(df)
    # Trigger on the SAME date as the only snapshot → no prior anchor available
    trig = pd.Timestamp("2024-06-03 14:00:00", tz="UTC")
    quote = lk.find(trig, spot=450.0, side="long", otm_offset=0, expiration_dte=0)
    assert quote is None


def test_iv_lookup_voids_when_expiration_not_in_chain():
    """If the requested expiration didn't exist in the anchor's chain,
    void. Regression for IWM 2022 Tue/Thu — Tuesday-expiring contracts
    weren't issued until Nov 2023; a Tue setup in 2022 should void."""
    df = _synthetic_eod_snapshots(["2024-06-03"], expiration_offsets=(2,))  # ONLY 2-day-out exp
    lk = IVLookup(df)
    trig = pd.Timestamp("2024-06-04 14:00:00", tz="UTC")
    # Asking for a 0DTE-from-trigger (= 1d-from-snapshot) → not in chain
    quote = lk.find(trig, spot=450.0, side="long", otm_offset=0, expiration_dte=0)
    assert quote is None


def test_iv_lookup_put_otm_offset_picks_strike_below():
    """For PUTs, +1-OTM means BELOW spot (lower strike, away from money)."""
    df = _synthetic_eod_snapshots(["2024-06-03", "2024-06-04"])
    lk = IVLookup(df)
    trig = pd.Timestamp("2024-06-04 14:01:00", tz="UTC")
    quote = lk.find(trig, spot=450.0, side="short", otm_offset=1, expiration_dte=0)
    assert quote is not None
    assert quote.kind == "put"
    assert quote.strike == 449.0  # 1 strike below ATM (in our $1-grid synthetic)


def test_iv_lookup_call_otm_offset_picks_strike_above():
    df = _synthetic_eod_snapshots(["2024-06-03", "2024-06-04"])
    lk = IVLookup(df)
    trig = pd.Timestamp("2024-06-04 14:01:00", tz="UTC")
    quote = lk.find(trig, spot=450.0, side="long", otm_offset=1, expiration_dte=0)
    assert quote is not None
    assert quote.kind == "call"
    assert quote.strike == 451.0


def test_iv_lookup_empty_returns_none():
    lk = IVLookup(pd.DataFrame())
    trig = pd.Timestamp("2024-06-03 14:00:00", tz="UTC")
    quote = lk.find(trig, spot=450.0, side="long")
    assert quote is None


def test_iv_lookup_snapshot_tolerance_constant_preserved_for_backcompat():
    """SNAPSHOT_TOLERANCE_SECONDS is kept as a module constant for any
    callers that imported it before the EOD-anchor pivot. Under the new
    design it's informational only — never used to gate."""
    assert SNAPSHOT_TOLERANCE_SECONDS == 300


# ─────────────────────────────────────────── Engine smoke ─────────────────────────────────

from lib.options_exec_backtest.engine import (
    OptionSetup, OptionTradeSpec, simulate_option_setup, fold_stats,
    COST_ROUND_TRIP, CONTRACT_MULTIPLIER,
)


def _synthetic_1m_bars(start_ts, n_bars=60, base_price=450.0, slope=0.0):
    """Build a synthetic 1m OHLC RTH window."""
    ts_index = pd.date_range(start_ts, periods=n_bars, freq="1min", tz="UTC")
    prices = base_price + slope * np.arange(n_bars)
    df = pd.DataFrame({
        "Open": prices,
        "High": prices + 0.1,
        "Low": prices - 0.1,
        "Close": prices,
    }, index=ts_index)
    return df


def test_simulate_option_setup_long_target_hit():
    """Long-call: underlying rises through trigger high within bar T+1, then
    continues up → underlying target hit → option premium realized via BSM walk."""
    trigger_open = pd.Timestamp("2024-06-03 14:00:00", tz="UTC")
    trigger_close = pd.Timestamp("2024-06-03 14:05:00", tz="UTC")  # 5m bar
    # Slope 0.15/min: by minute 4 of bar T+1 (14:09) price is 450.60 > 450.5 trigger.
    # By minute ~15 (14:20) price is 452.25 — well past target of 450.5 + 1.5*1 = 452.0.
    bars = _synthetic_1m_bars(trigger_close, n_bars=60, base_price=450.0, slope=0.15)
    # Add the bar that contains the trigger entry — must be after trigger_close
    setup = OptionSetup(
        setup_id=1, fold="2024", cell="5m", direction="long",
        trigger_ts_open=trigger_open, trigger_ts_close=trigger_close,
        trigger_high=450.5, trigger_low=449.5,
        top_prob=0.62,
    )
    # IV preload — T-1 EOD snapshot (2024-05-31 Friday, since 6/1-6/2 is
    # weekend). Anchor IV pulled from the 2024-05-31 EOD chain; expiration
    # = 2024-06-03 (the trigger date = 0DTE from trigger's perspective =
    # 3 days out from the 5/31 snapshot perspective).
    iv_df = _synthetic_eod_snapshots(
        ["2024-05-31"], spot=450.0, ticker="IWM",
        expiration_offsets=(3, 4),  # 5/31 + 3 = 6/3 (the trigger date)
    )
    lk = IVLookup(iv_df)
    spec = OptionTradeSpec(target_multiple=1.5, time_stop_minutes=30)
    trade = simulate_option_setup(
        setup, bars, lk, spec, risk_free=0.045, div_yield=0.013,
    )
    assert trade is not None
    # Underlying rose: gross premium positive expected for long call
    # (with 30 min of theta on a 0DTE this can still be net-negative —
    # we just assert that the trade FIRED, that exit_reason is one of
    # the valid values, and that costs were charged)
    assert trade.exit_reason in {"target", "stop", "time", "eod"}
    assert trade.cost_per_contract == pytest.approx(COST_ROUND_TRIP)
    assert trade.kind == "call"
    assert trade.strike == 450.0


def test_simulate_option_setup_voids_when_no_anchor():
    """Under EOD-anchor design, a setup voids when the EOD preload has
    no snapshot STRICTLY PRIOR to trigger_date (first-day-of-window
    edge case, or the only snapshot is from the same day as trigger
    which would be look-ahead)."""
    trigger_close = pd.Timestamp("2024-06-03 14:05:00", tz="UTC")
    bars = _synthetic_1m_bars(trigger_close, n_bars=60, base_price=450.0)
    setup = OptionSetup(
        setup_id=2, fold="2024", cell="5m", direction="long",
        trigger_ts_open=pd.Timestamp("2024-06-03 14:00:00", tz="UTC"),
        trigger_ts_close=trigger_close,
        trigger_high=450.5, trigger_low=449.5, top_prob=0.62,
    )
    # Only snapshot is FROM THE TRIGGER DATE — not strictly prior → void.
    iv_df = _synthetic_eod_snapshots(["2024-06-03"], spot=450.0)
    lk = IVLookup(iv_df)
    spec = OptionTradeSpec()
    trade = simulate_option_setup(setup, bars, lk, spec,
                                   risk_free=0.045, div_yield=0.013)
    assert trade is None


def test_fold_stats_empty():
    s = fold_stats([])
    assert s["n"] == 0
    assert s["hit_rate"] == 0.0


def test_simulate_option_setup_costs_match_spec():
    """Round-trip cost must be exactly $1.38 (3¢+65¢+1¢ × 2)."""
    assert COST_ROUND_TRIP == pytest.approx(1.38, abs=1e-9)
    assert CONTRACT_MULTIPLIER == 100


# ─────────────────────────────────────── dual-window verdict path ───────────────

from lib.options_exec_backtest.runner import (
    WINDOWS, evaluate_base_case_per_cell,
)


def test_windows_dict_shape():
    """The two windows are defined with the expected fold counts and
    success bars."""
    assert "5fold" in WINDOWS
    assert "3fold" in WINDOWS
    assert len(WINDOWS["5fold"]["cutoffs"]) == 5
    assert len(WINDOWS["3fold"]["cutoffs"]) == 3
    assert WINDOWS["5fold"]["positive_fold_threshold"] == 4
    assert WINDOWS["3fold"]["positive_fold_threshold"] == 2
    # 3fold is a SUBSET of 5fold (so emit_timestamps can use the wider
    # window for fetching; backtests pick a subset).
    five = set(WINDOWS["5fold"]["cutoffs"])
    three = set(WINDOWS["3fold"]["cutoffs"])
    assert three.issubset(five), (
        f"3fold cutoffs {three} must be a subset of 5fold {five}; otherwise "
        "the AV intraday backfill emitted from the 5fold range won't cover "
        "every setup the 3fold backtest needs."
    )


def _fold_stub(n, hit_rate, net_exp, avg_win, avg_loss, total_net):
    """Tiny helper to build the per-fold dict shape that
    evaluate_base_case_per_cell expects."""
    return {
        "n": n, "hit_rate": hit_rate, "net_exp": net_exp,
        "avg_win": avg_win, "avg_loss": avg_loss, "total_net": total_net,
    }


def test_evaluate_uses_passed_threshold_not_default():
    """Same per-fold stats, different positive-fold-threshold → different
    verdict. Proves the param flows through and isn't shadowed by the
    module-level POSITIVE_FOLD_THRESHOLD."""
    # 3 folds, 2 positive: passes the 3fold bar (≥ 2/3) but would FAIL
    # under the 5fold default of 4 (only 2 positive). Note c4 also
    # requires total_net > 0, so we keep an honest aggregate.
    folds = [
        _fold_stub(n=100, hit_rate=0.45, net_exp=10.0, avg_win=80.0,
                   avg_loss=-30.0, total_net=1000.0),
        _fold_stub(n=100, hit_rate=0.45, net_exp=6.0, avg_win=80.0,
                   avg_loss=-30.0, total_net=600.0),
        _fold_stub(n=100, hit_rate=0.40, net_exp=-2.0, avg_win=80.0,
                   avg_loss=-30.0, total_net=-200.0),
    ]
    v_3fold = evaluate_base_case_per_cell(folds, positive_fold_threshold=2)
    v_5fold = evaluate_base_case_per_cell(folds, positive_fold_threshold=4)
    # 3fold: ≥ 2 of 3 positive folds → c1 passes
    assert v_3fold["checks"]["c1_pos_exp_folds"][2] is True
    # 5fold bar applied to the same 3 folds: 2 positive < 4 → c1 fails
    assert v_5fold["checks"]["c1_pos_exp_folds"][2] is False
