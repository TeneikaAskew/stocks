"""Track 2 phase 2a — end-to-end live validation against Cloud SQL.

Runs as a one-shot Cloud Run Job. Inserts ~6 synthetic REALTIME rows for
a guaranteed-non-colliding contract (strike 99999.99 — impossible for SPY,
contract_symbol prefix 'TRACK2_TEST_'), exercises every new code path
against real Cloud SQL, then deletes the synthetic rows.

Validates:
    1. load_realtime_theta_curve emits SQL that round-trips correctly via
       cloud-sql-python-connector + pg8000 + Postgres
    2. load_realtime_marks does the same
    3. estimate_options_pnl dispatches realtime → mark-to-mark vs
       fallback → Greeks-approximation based on data presence
    4. reprice_intraday_option uses observed IV when realtime data exists
    5. data_source column populated correctly on every row

All assertions log PASS/FAIL via structured logging — readable via
``gcloud beta run jobs executions logs read``. Job exits non-zero if any
assertion fails so the Cloud Run execution surfaces as FAILED.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcp.database import get_engine, is_cloud_sql_configured
from lib.options_intraday import (
    DATA_SOURCE_EMPIRICAL_FALLBACK,
    DATA_SOURCE_REALTIME,
    load_realtime_theta_curve,
    reprice_intraday_option,
)
from scripts.analysis.options_pnl_translation import (
    estimate_options_pnl,
    find_realtime_mark_at,
    load_realtime_marks,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('track2-validation')

# Synthetic-data markers. Strike 99999.99 is impossibly high for SPY
# (no real chain row can collide). Contract symbol prefix is the cleanup
# anchor — even if INSERT crashes mid-batch, DELETE WHERE contract_symbol
# LIKE 'TRACK2_TEST_%' is safe and idempotent.
VALIDATION_DATE   = date(2026, 6, 12)
VALIDATION_STRIKE = 99999.99
VALIDATION_CONTRACT = 'TRACK2_TEST_C99999_v1'

# 6 synthetic snapshots at 5-min cadence covering the morning + early afternoon.
# Mark drifts up then down; IV crushes monotonically — realistic 0DTE shape.
SYNTHETIC_SNAPS = [
    # (UTC snapshot_ts, mark, IV, delta)
    ('2026-06-12 13:30:00+00', 2.50, 0.30, 0.50),
    ('2026-06-12 13:35:00+00', 2.55, 0.28, 0.51),
    ('2026-06-12 13:40:00+00', 2.90, 0.27, 0.55),
    ('2026-06-12 14:00:00+00', 3.20, 0.25, 0.60),
    ('2026-06-12 14:05:00+00', 3.00, 0.24, 0.58),
    ('2026-06-12 14:30:00+00', 2.15, 0.20, 0.45),
]


def insert_synthetic_rows():
    log.info("--- INSERT 6 synthetic REALTIME rows for %s ---",
             VALIDATION_CONTRACT)
    eng = get_engine()
    with eng.begin() as conn:
        for ts, mark, iv, delta in SYNTHETIC_SNAPS:
            conn.execute(text("""
                INSERT INTO etf_options_snapshots (
                    ticker, snapshot_ts, snapshot_date, market_session,
                    contract_symbol, option_type, expiration, strike,
                    bid, ask, mark, implied_volatility,
                    delta, gamma, theta, vega, rho,
                    data_source
                ) VALUES (
                    'SPY', :ts, '2026-06-12', 'REALTIME', :contract,
                    'calls', '2026-06-12', :strike,
                    :bid, :ask, :mark, :iv,
                    :delta, 0.02, -0.20, 0.10, 0.05,
                    'alphavantage'
                )
                ON CONFLICT (ticker, snapshot_ts, option_type, expiration, strike)
                DO UPDATE SET
                    mark = EXCLUDED.mark,
                    implied_volatility = EXCLUDED.implied_volatility,
                    delta = EXCLUDED.delta
            """), {
                'ts': ts, 'contract': VALIDATION_CONTRACT,
                'strike': VALIDATION_STRIKE,
                'bid': mark - 0.05, 'ask': mark + 0.05,
                'mark': mark, 'iv': iv, 'delta': delta,
            })
    log.info("Inserted/upserted %d rows", len(SYNTHETIC_SNAPS))


def cleanup_synthetic_rows():
    log.info("--- DELETE synthetic rows ---")
    eng = get_engine()
    with eng.begin() as conn:
        result = conn.execute(text(
            "DELETE FROM etf_options_snapshots "
            "WHERE contract_symbol LIKE 'TRACK2_TEST_%'"
        ))
        log.info("Deleted %d rows", result.rowcount)


def assert_eq(actual, expected, label):
    if actual == expected:
        log.info("  PASS  %s = %r", label, actual)
        return True
    log.error("  FAIL  %s: expected %r, got %r", label, expected, actual)
    return False


def assert_close(actual, expected, label, tol=1e-6):
    if abs(float(actual) - float(expected)) <= tol:
        log.info("  PASS  %s ≈ %r (got %r)", label, expected, actual)
        return True
    log.error("  FAIL  %s: expected ≈ %r, got %r (tol=%r)",
              label, expected, actual, tol)
    return False


def main():
    log.info("=" * 70)
    log.info("Track 2 phase 2a — LIVE VALIDATION against Cloud SQL")
    log.info("=" * 70)
    log.info("Project   : adept-mountain-474619-d4")
    log.info("Table     : etf_options_snapshots")
    log.info("Date      : %s", VALIDATION_DATE)
    log.info("Strike    : %s (synthetic — won't collide)", VALIDATION_STRIKE)
    log.info("Contract  : %s", VALIDATION_CONTRACT)

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — cannot validate")
        sys.exit(2)

    failures: list[str] = []

    try:
        insert_synthetic_rows()

        # ── Test 1 ── load_realtime_theta_curve ─────────────────────
        log.info("")
        log.info("=== TEST 1: load_realtime_theta_curve ===")
        curve = load_realtime_theta_curve(
            ticker='SPY', intraday_date=VALIDATION_DATE,
            expiration=VALIDATION_DATE, strike=VALIDATION_STRIKE,
            option_type='call',
        )
        if curve is None:
            log.error("  FAIL  curve is None — query returned no rows")
            failures.append("test_1_curve_is_none")
        else:
            log.info("  curve.shape = %s, columns = %s",
                     curve.shape, list(curve.columns))
            log.info("  curve:\n%s", curve.to_string(index=False))
            for ok, lbl in [
                (assert_eq(len(curve), 6, "len(curve)"), "test_1_len"),
                (assert_close(curve['implied_volatility'].iloc[0], 0.30,
                              "first IV"), "test_1_first_iv"),
                (assert_close(curve['implied_volatility'].iloc[-1], 0.20,
                              "last IV"), "test_1_last_iv"),
                (assert_close(curve['mark'].iloc[0], 2.50, "first mark"),
                 "test_1_first_mark"),
                (assert_close(curve['delta'].iloc[2], 0.55, "delta[2]"),
                 "test_1_delta"),
            ]:
                if not ok:
                    failures.append(lbl)

        # ── Test 2 ── load_realtime_marks ───────────────────────────
        log.info("")
        log.info("=== TEST 2: load_realtime_marks ===")
        marks = load_realtime_marks(
            ticker='SPY', trade_date=VALIDATION_DATE,
            expiration=VALIDATION_DATE, strike=VALIDATION_STRIKE,
            option_type='call',
        )
        if marks.empty:
            log.error("  FAIL  marks is empty")
            failures.append("test_2_marks_empty")
        else:
            log.info("  marks.shape = %s, columns = %s",
                     marks.shape, list(marks.columns))
            log.info("  marks:\n%s", marks.to_string(index=False))
            for ok, lbl in [
                (assert_eq(len(marks), 6, "len(marks)"), "test_2_len"),
                (assert_close(marks['mark'].iloc[0], 2.50, "first mark"),
                 "test_2_first"),
                (assert_close(marks['mark'].iloc[-1], 2.15, "last mark"),
                 "test_2_last"),
                (assert_close(marks['bid'].iloc[0], 2.45, "first bid"),
                 "test_2_bid"),
            ]:
                if not ok:
                    failures.append(lbl)

        # ── Test 3 ── find_realtime_mark_at with real marks ─────────
        log.info("")
        log.info("=== TEST 3: find_realtime_mark_at nearest-snapshot match ===")
        if not marks.empty:
            target = datetime.combine(VALIDATION_DATE, datetime.min.time(),
                                       tzinfo=timezone.utc) \
                     + timedelta(hours=13, minutes=37)  # 13:37 UTC = 9:37 ET
            obs = find_realtime_mark_at(marks, target)
            if obs.empty:
                log.error("  FAIL  expected a snapshot within ±5 min of 13:37")
                failures.append("test_3_no_match")
            else:
                log.info("  matched snapshot_ts = %s, mark = %s",
                         obs['snapshot_ts'], obs['mark'])
                # 13:37 is closer to 13:35 (2 min) than 13:40 (3 min)
                if not assert_close(obs['mark'], 2.55,
                                    "matched mark (expected 13:35 snapshot)"):
                    failures.append("test_3_wrong_match")

        # ── Test 4 ── estimate_options_pnl REALTIME branch ──────────
        log.info("")
        log.info("=== TEST 4: estimate_options_pnl REALTIME branch ===")
        # Trade: entry 13:35 UTC, hold 30 min → exit 14:05 UTC
        # Realtime bracket: mark_entry=2.55, mark_exit=3.00, spread=0.05
        # Expected realized = 3.00 - 2.55 - 0.05 = 0.40
        trade = pd.Series({
            'trade_date':  VALIDATION_DATE,
            'direction':   'CALL',
            'entry_price': 600.0,
            'entry_time':  datetime.combine(VALIDATION_DATE,
                                             datetime.min.time(),
                                             tzinfo=timezone.utc)
                            + timedelta(hours=13, minutes=35),
            'return_pct':  0.005,
            'hold_min':    30.0,
            'hhmm':        935,
        })
        atm = pd.Series({
            'strike': VALIDATION_STRIKE, 'mark': 2.50,
            'bid': 2.45, 'ask': 2.55,
            'delta': 0.50, 'theta': -0.20,
            'expiration': VALIDATION_DATE, 'type': 'call',
        })
        rt_result = estimate_options_pnl(trade, atm, realtime_marks=marks)
        if rt_result is None:
            log.error("  FAIL  rt_result is None")
            failures.append("test_4_none")
        else:
            log.info("  rt_result: %s",
                     {k: round(v, 4) if isinstance(v, float) else v
                      for k, v in rt_result.items()})
            for ok, lbl in [
                (assert_eq(rt_result['data_source'], DATA_SOURCE_REALTIME,
                           "data_source"), "test_4_ds"),
                (assert_close(rt_result['net_pnl_dollar'], 0.40,
                              "net_pnl_dollar", tol=0.01), "test_4_pnl"),
                (assert_eq(pd.isna(rt_result['delta_pnl']), True,
                           "delta_pnl is NaN"), "test_4_delta_nan"),
                (assert_eq(pd.isna(rt_result['theta_cost']), True,
                           "theta_cost is NaN"), "test_4_theta_nan"),
                (assert_eq(rt_result['option_win'], 1, "option_win"),
                 "test_4_win"),
            ]:
                if not ok:
                    failures.append(lbl)

        # ── Test 5 ── estimate_options_pnl FALLBACK branch ──────────
        log.info("")
        log.info("=== TEST 5: estimate_options_pnl FALLBACK branch ===")
        fb_result = estimate_options_pnl(trade, atm, realtime_marks=None)
        if fb_result is None:
            log.error("  FAIL  fb_result is None")
            failures.append("test_5_none")
        else:
            log.info("  fb_result: %s",
                     {k: round(v, 4) if isinstance(v, float) else v
                      for k, v in fb_result.items()})
            for ok, lbl in [
                (assert_eq(fb_result['data_source'],
                           DATA_SOURCE_EMPIRICAL_FALLBACK, "data_source"),
                 "test_5_ds"),
                (assert_close(fb_result['delta_pnl'], 1.50,
                              "delta_pnl = 0.5*|600*0.005|", tol=0.01),
                 "test_5_delta_pnl"),
            ]:
                if not ok:
                    failures.append(lbl)

            # SIDE-BY-SIDE comparison — the "why this matters" line
            log.info("")
            log.info("  *** SIDE-BY-SIDE comparison ***")
            log.info("    Realtime  net_pnl_dollar = %+.3f  (%s)",
                     rt_result['net_pnl_dollar'], rt_result['data_source'])
            log.info("    Fallback  net_pnl_dollar = %+.3f  (%s)",
                     fb_result['net_pnl_dollar'], fb_result['data_source'])
            delta = rt_result['net_pnl_dollar'] - fb_result['net_pnl_dollar']
            log.info("    Delta     = %+.3f  ← realtime measures realized; "
                     "fallback estimates from EOD Greeks", delta)

        # ── Test 6 ── reprice_intraday_option realtime IV path ──────
        log.info("")
        log.info("=== TEST 6: reprice_intraday_option observed IV path ===")
        # Synthetic 1-min bars covering 9:30-10:30 ET (13:30-14:30 UTC)
        bars = pd.DataFrame({
            'Time': [datetime.combine(VALIDATION_DATE, datetime.min.time())
                     + timedelta(minutes=m)
                     for m in [9*60+30, 9*60+35, 9*60+40, 10*60+0,
                               10*60+5, 10*60+30]],
            'Spot': [600.0, 600.5, 601.0, 601.5, 601.0, 600.0],
        })
        tl = reprice_intraday_option(
            ticker='SPY', intraday_date=VALIDATION_DATE,
            strike=VALIDATION_STRIKE, expiration=VALIDATION_DATE,
            option_type='call', iv_t_minus_1=0.60,
            entry_price_per_share=2.50,
            intraday_bars=bars,
            risk_free=0.045, dividend_yield=0.013,
        )
        log.info("  timeline.shape = %s", tl.shape)
        log.info("  timeline:\n%s",
                 tl[['Time', 'Spot', 'IV_used', 'Theo_value',
                     'data_source']].to_string(index=False))
        for ok, lbl in [
            (assert_eq((tl['data_source'] == DATA_SOURCE_REALTIME).all(),
                       True, "all rows tagged REALTIME"), "test_6_ds"),
            (assert_close(tl['IV_used'].iloc[0], 0.30,
                          "first IV (observed open)"), "test_6_iv_first"),
            (assert_close(tl['IV_used'].iloc[-1], 0.20,
                          "last IV (observed close)"), "test_6_iv_last"),
        ]:
            if not ok:
                failures.append(lbl)

    finally:
        cleanup_synthetic_rows()

    # ── Summary ─────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    if failures:
        log.error("VALIDATION FAILED — %d assertion(s) failed: %s",
                  len(failures), failures)
        sys.exit(1)
    else:
        log.info("VALIDATION PASSED — every code path round-tripped "
                 "against real Cloud SQL")
        log.info("=" * 70)


if __name__ == '__main__':
    main()
