"""Unit tests for gcp.premarket_playbook_resolver.resolve_leg.

These tests focus on the bar-walking math (no DB I/O). Each test
constructs a small DataFrame of synthetic 1-min bars and asserts that
trigger / target / stop / MAE / MFE / EOD pnl land where expected.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from gcp.premarket_playbook_resolver import resolve_leg, LegOutcome


def _bar(t: datetime, open_: float, high: float, low: float, close: float) -> dict:
    return {'time': t, 'open': open_, 'high': high, 'low': low, 'close': close}


def _bars(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    return df


# Convenience: a base RTH timestamp = 2026-05-06 13:30 UTC = 09:30 ET
T0 = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)


def _ts(minute_offset: int) -> datetime:
    return T0 + timedelta(minutes=minute_offset)


# ─── 1. CALL never triggers ─────────────────────────────────────────────
def test_call_never_triggers_returns_empty_outcome():
    bars = _bars([
        _bar(_ts(0), 100, 100.5, 99.8, 100.2),
        _bar(_ts(1), 100.2, 100.6, 100.0, 100.4),
        _bar(_ts(2), 100.4, 100.7, 100.1, 100.3),
    ])
    out = resolve_leg('call', trigger_price=105.0, stop_price=99.0,
                     target_prices=[106.0, 107.0, 108.0], bars=bars)
    assert out.trigger_hit_ts is None
    assert out.t1_hit_ts is None
    assert out.eod_pnl_pct is None
    assert out.eod_pnl_dollar is None
    assert out.mae_pct is None
    assert out.mfe_pct is None


# ─── 2. CALL triggers, hits T1 only ────────────────────────────────────
def test_call_triggers_and_hits_t1_only_pnl_at_t1():
    # trigger=100, t1=101, t2=103, t3=105, stop=99
    # bars: trigger at minute 1, T1 at minute 3, no further targets
    bars = _bars([
        _bar(_ts(0), 99.5, 99.8, 99.4, 99.7),
        _bar(_ts(1), 99.7, 100.2, 99.6, 100.1),  # high >= trigger
        _bar(_ts(2), 100.1, 100.5, 99.9, 100.3),
        _bar(_ts(3), 100.3, 101.1, 100.2, 100.9),  # high >= T1
        _bar(_ts(4), 100.9, 101.05, 100.5, 100.7),
        _bar(_ts(5), 100.7, 100.9, 100.4, 100.6),  # EOD close
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0, 103.0, 105.0], bars=bars,
                     notional=10000.0)
    assert out.trigger_hit_ts == bars.iloc[1]['time']
    assert out.t1_hit_ts == bars.iloc[3]['time']
    assert out.t2_hit_ts is None
    assert out.t3_hit_ts is None
    assert out.stop_hit_ts is None
    assert out.reversal_after_trigger is False
    assert out.time_to_t1_min == 2
    # realized = T1 (101); pnl = (101-100)/100*100 = 1.0%
    assert out.eod_pnl_pct == pytest.approx(1.0)
    assert out.eod_pnl_dollar == pytest.approx(100.0)


# ─── 3. CALL hits all 3 targets — realized at T3 ───────────────────────
def test_call_hits_all_targets_realized_at_t3():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),  # trigger
        _bar(_ts(1), 100.0, 101.5, 99.9, 101.0),  # T1
        _bar(_ts(2), 101.0, 103.2, 100.8, 103.0),  # T2
        _bar(_ts(3), 103.0, 105.5, 102.8, 105.0),  # T3
        _bar(_ts(4), 105.0, 105.2, 104.5, 104.8),
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0, 103.0, 105.0], bars=bars,
                     notional=10000.0)
    assert out.t1_hit_ts == bars.iloc[1]['time']
    assert out.t2_hit_ts == bars.iloc[2]['time']
    assert out.t3_hit_ts == bars.iloc[3]['time']
    assert out.stop_hit_ts is None
    # realized = T3 (105); pnl = 5%; dollars = 500
    assert out.eod_pnl_pct == pytest.approx(5.0)
    assert out.eod_pnl_dollar == pytest.approx(500.0)


# ─── 4. CALL triggers, then reverses to stop ───────────────────────────
def test_call_reversal_to_stop_realized_at_stop():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),  # trigger
        _bar(_ts(1), 100.0, 100.3, 99.7, 99.8),
        _bar(_ts(2), 99.8, 99.9, 98.8, 99.0),    # stop hit (low <= 99)
        _bar(_ts(3), 99.0, 99.2, 98.5, 98.7),
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0, 103.0, 105.0], bars=bars,
                     notional=10000.0)
    assert out.trigger_hit_ts == bars.iloc[0]['time']
    assert out.stop_hit_ts == bars.iloc[2]['time']
    assert out.reversal_after_trigger is True
    assert out.t1_hit_ts is None
    # realized = stop (99); pnl = (99-100)/100*100 = -1%
    assert out.eod_pnl_pct == pytest.approx(-1.0)
    assert out.eod_pnl_dollar == pytest.approx(-100.0)


# ─── 5. CALL triggers, no stop, no target — EOD close ──────────────────
def test_call_neither_stop_nor_target_eod_close():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),  # trigger at high=100.2
        _bar(_ts(1), 100.0, 100.5, 99.6, 100.3),
        _bar(_ts(2), 100.3, 100.4, 99.8, 100.1),  # EOD close
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0], bars=bars, notional=10000.0)
    assert out.trigger_hit_ts == bars.iloc[0]['time']
    assert out.stop_hit_ts is None
    assert out.t1_hit_ts is None
    # realized = EOD close (100.1); pnl = 0.1%
    assert out.eod_pnl_pct == pytest.approx(0.1, abs=1e-3)
    assert out.eod_pnl_dollar == pytest.approx(10.0, abs=0.5)


# ─── 6. PUT mirror — triggers via low, stop via high ───────────────────
def test_put_triggers_hits_t1_realized_pnl_positive_for_short():
    # PUT: trigger=100 means low <= 100 to fire
    # stop=101 means high >= 101 reverses
    # T1=99 means low <= 99 reaches
    bars = _bars([
        _bar(_ts(0), 100.5, 100.6, 100.4, 100.5),
        _bar(_ts(1), 100.5, 100.5, 99.9, 100.0),  # trigger (low <= 100)
        _bar(_ts(2), 100.0, 100.1, 98.9, 99.0),   # T1 (low <= 99)
        _bar(_ts(3), 99.0, 99.3, 98.7, 99.1),
    ])
    out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                     target_prices=[99.0, 97.0], bars=bars,
                     notional=10000.0)
    assert out.trigger_hit_ts == bars.iloc[1]['time']
    assert out.t1_hit_ts == bars.iloc[2]['time']
    assert out.stop_hit_ts is None
    # realized = T1 (99); short pnl = -1 * (99-100)/100 * 100 = +1%
    assert out.eod_pnl_pct == pytest.approx(1.0)


# ─── 7. PUT — stop hit (price went up against the short) ───────────────
def test_put_stop_hit_negative_pnl():
    bars = _bars([
        _bar(_ts(0), 100.5, 100.6, 99.9, 100.0),  # trigger via low
        _bar(_ts(1), 100.0, 101.2, 99.9, 101.0),  # stop via high >= 101
        _bar(_ts(2), 101.0, 101.5, 100.5, 101.2),
    ])
    out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                     target_prices=[99.0], bars=bars, notional=10000.0)
    assert out.stop_hit_ts == bars.iloc[1]['time']
    assert out.reversal_after_trigger is True
    # realized = stop (101); short pnl = -1 * (101-100)/100*100 = -1%
    assert out.eod_pnl_pct == pytest.approx(-1.0)
    assert out.eod_pnl_dollar == pytest.approx(-100.0)


# ─── 8. Empty bars → empty outcome ─────────────────────────────────────
def test_empty_bars_returns_empty_outcome():
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0], bars=pd.DataFrame())
    assert out.trigger_hit_ts is None
    assert out.eod_pnl_pct is None


# ─── 9. Missing trigger price → empty outcome ──────────────────────────
def test_missing_trigger_price_returns_empty():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
    ])
    out = resolve_leg('call', trigger_price=None, stop_price=99.0,
                     target_prices=[101.0], bars=bars)
    assert out.trigger_hit_ts is None
    assert out.eod_pnl_pct is None


# ─── 10. MFE/MAE accuracy ──────────────────────────────────────────────
def test_call_mfe_mae_accuracy():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),  # trigger at 100
        _bar(_ts(1), 100.0, 102.0, 99.5, 101.5),  # high 102 → MFE 2%, low 99.5 → MAE 0.5%
        _bar(_ts(2), 101.5, 102.5, 99.0, 100.0),  # high 102.5, low 99.0 → MAE 1%
        _bar(_ts(3), 100.0, 100.2, 99.8, 100.0),
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=98.0,
                     target_prices=[110.0], bars=bars)  # T1 unreachable
    # MFE = (102.5 - 100) / 100 * 100 = 2.5
    # MAE = (100 - 99.0) / 100 * 100 = 1.0
    assert out.mfe_pct == pytest.approx(2.5)
    assert out.mae_pct == pytest.approx(1.0)


# ─── 11. Stop and T1 hit in SAME bar — stop wins (conservative) ────────
def test_call_stop_and_t1_same_bar_stop_takes_priority():
    # The bar's high reaches T1 AND its low reaches stop. The resolver's
    # convention: if stop_hit_ts <= t1_hit_ts, realize at stop.
    # In this scenario both timestamps are equal, so stop wins.
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),    # trigger
        _bar(_ts(1), 100.0, 101.5, 98.5, 99.5),    # both T1 hi and stop lo
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0], bars=bars, notional=10000.0)
    assert out.t1_hit_ts == bars.iloc[1]['time']
    assert out.stop_hit_ts == bars.iloc[1]['time']
    # tied timestamps → stop_hit_ts <= t1_hit_ts → realize at stop
    assert out.eod_pnl_pct == pytest.approx(-1.0)
    assert out.reversal_after_trigger is True


# ─── 12. T1 hits before stop → realize at LAST target hit ──────────────
def test_call_t2_then_stop_realizes_at_t2_not_stop():
    # Trade reaches T1 then T2, then later stop. Conservative interpretation
    # used by this resolver: the LAST target reached before EOD is the
    # realized exit IF stop did not hit before that target.
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),    # trigger
        _bar(_ts(1), 100.0, 101.5, 99.9, 101.2),   # T1
        _bar(_ts(2), 101.2, 103.5, 101.0, 103.2),  # T2
        _bar(_ts(3), 103.2, 103.4, 98.5, 99.0),    # stop AFTER T2
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                     target_prices=[101.0, 103.0], bars=bars, notional=10000.0)
    assert out.t2_hit_ts == bars.iloc[2]['time']
    assert out.stop_hit_ts == bars.iloc[3]['time']
    assert out.reversal_after_trigger is True
    # realized at T2 (103); pnl = 3%
    assert out.eod_pnl_pct == pytest.approx(3.0)
    assert out.eod_pnl_dollar == pytest.approx(300.0)


# ─── 13. Reversal flag false when no stop hit ──────────────────────────
def test_call_reversal_false_when_no_stop():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
        _bar(_ts(1), 100.0, 101.5, 99.9, 101.2),
    ])
    out = resolve_leg('call', trigger_price=100.0, stop_price=98.0,
                     target_prices=[101.0], bars=bars)
    assert out.reversal_after_trigger is False


# ─── 14. Notional scaling ──────────────────────────────────────────────
def test_pnl_dollar_scales_with_notional():
    bars = _bars([
        _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
        _bar(_ts(1), 100.0, 101.5, 99.9, 101.2),
    ])
    out_10k = resolve_leg('call', 100.0, 99.0, [101.0], bars, notional=10_000.0)
    out_100k = resolve_leg('call', 100.0, 99.0, [101.0], bars, notional=100_000.0)
    assert out_100k.eod_pnl_dollar == pytest.approx(out_10k.eod_pnl_dollar * 10)
