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


# ─── 3. CALL hits all 3 targets — realized at T1 since cross-fill-t1-v1 ──
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
    # FEAT-SIGNAL-001 rule cross-fill-t1-v1 (a recorded change of rule): the
    # trade is all out at the first of the stop or T1, so it realizes at T1
    # (101), not the farthest target reached. origin/main booked T3 (5.0%).
    assert out.exit_reason == 't1'
    assert out.eod_pnl_pct == pytest.approx(1.0)
    assert out.eod_pnl_dollar == pytest.approx(100.0)


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


# ─── 12. T1 hits before stop → realize at T1 (all out at the first exit) ─
def test_call_t2_then_stop_realizes_at_t2_not_stop():
    # Trade reaches T1 then T2, then later stop. Until 2026-11-11 the LAST
    # target reached was booked; rule cross-fill-t1-v1 exits all at T1.
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
    # FEAT-SIGNAL-001 rule cross-fill-t1-v1 (a recorded change of rule): T1
    # then T2 then the stop realizes at T1 (101), all out at the first exit.
    # origin/main booked the last target reached, T2 (3.0%).
    assert out.exit_reason == 't1'
    assert out.eod_pnl_pct == pytest.approx(1.0)
    assert out.eod_pnl_dollar == pytest.approx(100.0)


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


# ─── classify_date_outcome — sweep-mode exit semantics ──────────────────
# The 2026-06-19 → 2026-08-25 outage happened because a same-day "no bars"
# skip (the 16:30 ET run racing the ~21:00 ET intraday ingestion) exited 0
# and the date was never revisited. These pin the classification that makes
# that mode impossible: benign only for today-before-cutoff, red otherwise.

from datetime import date as _date
from zoneinfo import ZoneInfo as _ZoneInfo

from gcp.premarket_playbook_resolver import classify_date_outcome, pending_dates

_ET_TZ = _ZoneInfo('America/New_York')


def test_classify_resolved_rows_is_ok():
    now = datetime(2026, 8, 25, 21, 30, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 8, 25), 3, 0, now) == 'ok'


def test_classify_partial_resolution_is_ok():
    now = datetime(2026, 8, 25, 21, 30, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 8, 25), 1, 2, now) == 'ok'


def test_classify_nothing_attempted_is_ok():
    now = datetime(2026, 8, 25, 21, 30, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 8, 25), 0, 0, now) == 'ok'


def test_classify_same_day_all_skipped_is_benign_any_hour():
    # Ingestion time varies by weekday (Tue-Fri ~21:00 ET, Mon ~23:00 ET),
    # so a same-day all-skip is always the pre-ingestion race; the sweep
    # picks the date up on the next run. A real outage alarms the next
    # night when the date ages into 'past'.
    for hour in (16, 21, 23):
        now = datetime(2026, 8, 25, hour, 30, tzinfo=_ET_TZ)
        assert classify_date_outcome(_date(2026, 8, 25), 0, 3, now) == 'benign_pending'


def test_classify_past_date_all_skipped_is_failed():
    # A past date can never be a pre-ingestion race, whatever the hour.
    now = datetime(2026, 8, 25, 16, 30, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 8, 24), 0, 3, now) == 'failed'


def test_classify_past_holiday_all_skipped_is_benign_holiday():
    # Reproduces #1068: 2026-09-07 is Labor Day (a weekday brief row with
    # no session — market_data_intraday will never have bars for it).
    # The 09-08 sweep found it all-skipped and classified it 'failed',
    # and would have kept re-firing 'failed' every day through 09-21
    # (the end of the 14-day lookback window) without this case.
    now = datetime(2026, 9, 8, 21, 15, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 9, 7), 0, 3, now) == 'benign_holiday'


def test_classify_past_non_holiday_all_skipped_still_fails_next_to_a_holiday():
    # The holiday exception must not swallow a real gap on an adjacent
    # ordinary trading day — only the exact holiday date is benign.
    now = datetime(2026, 9, 9, 21, 15, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2026, 9, 8), 0, 3, now) == 'failed'


def test_pending_dates_normalizes_postgres_timestamps_to_plain_date(monkeypatch):
    # Codex review on #1075 (P1): pd.read_sql returns pandas.Timestamp for a
    # Postgres DATE column, and Timestamp is a datetime which is a date, so
    # the old `d if isinstance(d, date) else d.date()` check never converted
    # it. A Timestamp compares unequal to every plain `date` (different
    # classes never compare equal in Python), so classify_date_outcome's
    # `analysis_date == now_et.date()` and its holiday-set membership check
    # (a 2026-only set then, the shared NYSE calendar now) were both silently
    # unreachable against pending_dates()'s real output — the holiday fix in
    # this same PR would not have actually fired in production without this.
    import gcp.premarket_playbook_resolver as mod

    def _fake_read_sql(sql, engine, params=None):
        return pd.DataFrame({'analysis_date': [pd.Timestamp('2026-09-07')]})

    monkeypatch.setattr(mod.pd, 'read_sql', _fake_read_sql)

    result = pending_dates(engine=object(), today_et=_date(2026, 9, 9), lookback_days=14)

    assert result == [_date(2026, 9, 7)]
    assert type(result[0]) is _date, f"expected plain date, got {type(result[0])!r}"


def test_classify_black_friday_all_skipped_still_fails():
    # Codex review on #1075: the freshness audit's old 2026-only holiday set
    # marked 2026-11-27 (Black Friday) "early close, treated as closed" for
    # its OWN staleness-tolerance purposes, but NYSE trades an abbreviated
    # session that day (13:00 ET close) — bars do land. Treating it as a
    # closure here would have given a real ingestion gap on Black Friday a
    # free pass all the way through the lookback window, the exact
    # false-negative this resolver's sweep design exists to prevent. The
    # shared NYSE calendar (FEAT-DATA-001) reports it as a session.
    now = datetime(2026, 11, 30, 21, 15, tzinfo=_ET_TZ)  # next weekday sweep
    assert classify_date_outcome(_date(2026, 11, 27), 0, 3, now) == 'failed'


# FEAT-DATA-001: the resolver reads the shared NYSE calendar
# (lib/eastern_time.is_session), so a closure in any year is benign, not only
# the 2026 dates the old hard-coded set listed.


def test_classify_2025_independence_day_is_benign_holiday():
    # A pre-2026 backfill (PLAYBOOK_RESOLVE_DATE=2025-07-04): NYSE was closed.
    now = datetime(2025, 7, 7, 21, 15, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2025, 7, 4), 0, 3, now) == 'benign_holiday'


def test_classify_2027_mlk_day_is_benign_holiday():
    # 2027-01-18 (MLK Day): the old 2026-only set expired on 2027-01-01 and
    # would have classified this 'failed' (the #1068 incident class, #1076).
    now = datetime(2027, 1, 19, 21, 15, tzinfo=_ET_TZ)
    assert classify_date_outcome(_date(2027, 1, 18), 0, 3, now) == 'benign_holiday'


# ─── FEAT-SIGNAL-001: honest outcome scoring, rule cross-fill-t1-v1 ──────
# docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md
# The fill is the trigger when the bar that first reaches it opened on the
# near side, that bar's own open when it opened beyond, and no entry at all
# when the session's first bar opened at or beyond it. The exit is all out at
# the first of the stop (any bar from the fill bar, a tie goes to the stop, a
# later bar opening beyond the stop exits at that open) or T1 (only from the
# bar after the fill, at the T1 price), else the last RTH close. Touch
# timestamps, excursions and the reversal flag are computed as before.


class TestCrossFillT1Rule:
    def test_call_session_open_at_or_above_trigger_is_gap_through(self):
        for first_open in (100.05, 100.0):
            bars = _bars([
                _bar(_ts(0), first_open, 101.4, 100.0, 101.2),
                _bar(_ts(1), 101.2, 101.6, 100.8, 101.5),
                _bar(_ts(2), 101.5, 101.7, 101.1, 101.3),
            ])
            out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                              target_prices=[101.0, 102.0, 103.0], bars=bars)
            assert out.entry_status == 'gap_through'
            assert out.fill_price is None
            assert out.exit_reason is None
            assert out.eod_pnl_pct is None
            assert out.eod_pnl_dollar is None
            # The touch record is unchanged: the trigger was reached on bar 0.
            assert out.trigger_hit_ts == bars.iloc[0]['time']
            assert out.t1_hit_ts == bars.iloc[0]['time']

    def test_put_session_open_at_or_below_trigger_is_gap_through(self):
        bars = _bars([
            _bar(_ts(0), 99.9, 100.1, 98.7, 98.8),
            _bar(_ts(1), 98.8, 99.0, 98.5, 98.6),
        ])
        out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                          target_prices=[99.0, 98.0], bars=bars)
        assert out.entry_status == 'gap_through'
        assert out.fill_price is None and out.eod_pnl_pct is None
        assert out.trigger_hit_ts == bars.iloc[0]['time']

    def test_call_later_bar_opening_above_trigger_fills_at_its_open(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 99.8, 99.4, 99.7),
            _bar(_ts(1), 99.7, 99.9, 99.6, 99.8),
            _bar(_ts(2), 100.6, 100.9, 100.5, 100.8),   # gaps over 100.00
            _bar(_ts(3), 100.8, 100.9, 100.4, 100.5),   # last close
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[102.0], bars=bars, notional=10000.0)
        assert out.entry_status == 'filled'
        assert out.fill_price == pytest.approx(100.6)
        assert out.exit_reason == 'close'
        # Measured from the fill, not the trigger: (100.5 - 100.6) / 100.6.
        assert out.eod_pnl_pct == pytest.approx(round(-0.1 / 100.6 * 100, 4))
        assert out.eod_pnl_dollar == pytest.approx(round(out.eod_pnl_pct / 100 * 10000, 2))
        assert out.trigger_hit_ts == bars.iloc[2]['time']
        assert out.mfe_pct == pytest.approx(0.9)        # still from the trigger

    def test_put_later_bar_opening_below_trigger_fills_at_its_open(self):
        bars = _bars([
            _bar(_ts(0), 100.5, 100.6, 100.2, 100.3),
            _bar(_ts(1), 99.4, 99.6, 99.2, 99.5),       # gaps under 100.00
            _bar(_ts(2), 99.5, 99.7, 99.3, 99.6),
        ])
        out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                          target_prices=[98.0], bars=bars)
        assert out.entry_status == 'filled'
        assert out.fill_price == pytest.approx(99.4)
        assert out.exit_reason == 'close'
        assert out.eod_pnl_pct == pytest.approx(round((99.4 - 99.6) / 99.4 * 100, 4))

    def test_target_touched_on_the_fill_bar_is_not_an_exit(self):
        # Bar 0 opens below the trigger, crosses it and also touches T1; T1
        # counts only from the next bar, which never reaches it again.
        bars = _bars([
            _bar(_ts(0), 99.5, 101.2, 99.4, 100.8),
            _bar(_ts(1), 100.8, 100.9, 100.3, 100.6),
            _bar(_ts(2), 100.6, 100.7, 100.4, 100.5),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0, 102.0], bars=bars)
        assert out.fill_price == pytest.approx(100.0)
        assert out.exit_reason == 'close'
        assert out.eod_pnl_pct == pytest.approx(0.5)
        assert out.t1_hit_ts == bars.iloc[0]['time']     # the touch is still recorded

    def test_call_t1_then_t2_then_stop_realizes_at_t1(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
            _bar(_ts(1), 100.0, 101.3, 99.9, 101.2),    # T1
            _bar(_ts(2), 101.2, 102.4, 101.0, 102.2),   # T2
            _bar(_ts(3), 102.2, 103.2, 102.0, 103.1),   # T3
            _bar(_ts(4), 103.1, 103.2, 98.0, 98.5),     # stop
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0, 102.0, 103.0], bars=bars)
        assert out.exit_reason == 't1'
        assert out.eod_pnl_pct == pytest.approx(1.0)
        assert (out.t1_hit_ts, out.t2_hit_ts, out.t3_hit_ts, out.stop_hit_ts) == tuple(
            bars.iloc[k]['time'] for k in (1, 2, 3, 4))

    def test_stop_and_t1_on_the_same_later_bar_realize_at_the_stop(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
            _bar(_ts(1), 100.0, 101.5, 98.5, 99.5),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0], bars=bars)
        assert out.exit_reason == 'stop'
        assert out.eod_pnl_pct == pytest.approx(-1.0)

    def test_stop_touched_on_the_fill_bar_realizes_at_the_stop(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 100.3, 98.9, 99.2),
            _bar(_ts(1), 99.2, 101.5, 99.1, 101.4),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0], bars=bars)
        assert out.exit_reason == 'stop'
        assert out.eod_pnl_pct == pytest.approx(-1.0)

    def test_call_later_bar_opening_below_the_stop_exits_at_that_open(self):
        # Filled at 100 with stop 99; a later bar opens at 97: -3.0%, where
        # origin/main booked the stop price, -1.0%.
        bars = _bars([
            _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
            _bar(_ts(1), 100.0, 100.4, 99.6, 99.8),
            _bar(_ts(2), 97.0, 97.5, 96.8, 97.2),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0], bars=bars, notional=10000.0)
        assert out.fill_price == pytest.approx(100.0)
        assert out.exit_reason == 'stop'
        assert out.eod_pnl_pct == pytest.approx(-3.0)
        assert out.eod_pnl_dollar == pytest.approx(-300.0)
        assert out.stop_hit_ts == bars.iloc[2]['time']

    def test_put_later_bar_opening_above_the_stop_exits_at_that_open(self):
        bars = _bars([
            _bar(_ts(0), 100.5, 100.6, 99.9, 100.0),
            _bar(_ts(1), 100.0, 100.4, 99.7, 100.2),
            _bar(_ts(2), 103.0, 103.4, 102.8, 103.1),
        ])
        out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                          target_prices=[99.0], bars=bars)
        assert out.fill_price == pytest.approx(100.0)
        assert out.exit_reason == 'stop'
        assert out.eod_pnl_pct == pytest.approx(-3.0)

    def test_later_bar_opening_beyond_t1_books_t1_not_the_open(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
            _bar(_ts(1), 101.5, 101.8, 101.4, 101.6),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0], bars=bars)
        assert out.exit_reason == 't1'
        assert out.eod_pnl_pct == pytest.approx(1.0)

    def test_put_later_bar_opening_beyond_t1_books_t1(self):
        bars = _bars([
            _bar(_ts(0), 100.5, 100.6, 99.9, 100.0),
            _bar(_ts(1), 98.5, 98.7, 98.2, 98.4),
        ])
        out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                          target_prices=[99.0], bars=bars)
        assert out.exit_reason == 't1'
        assert out.eod_pnl_pct == pytest.approx(1.0)

    def test_targets_at_or_behind_the_fill_are_skipped(self):
        # A later bar gaps to 101.5 over the 100.00 trigger: T1 101.0 is
        # behind the fill and T2 101.5 is at it, so T3 103.0 is the exit target.
        bars = _bars([
            _bar(_ts(0), 99.5, 99.8, 99.4, 99.7),
            _bar(_ts(1), 101.5, 101.9, 101.4, 101.8),
            _bar(_ts(2), 101.8, 102.6, 101.6, 102.5),
            _bar(_ts(3), 102.5, 103.1, 102.4, 103.0),
        ])
        out = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0, 101.5, 103.0], bars=bars)
        assert out.fill_price == pytest.approx(101.5)
        assert out.exit_reason == 't1'
        assert out.eod_pnl_pct == pytest.approx(round(1.5 / 101.5 * 100, 4))

    def test_put_targets_at_or_behind_the_fill_are_skipped(self):
        bars = _bars([
            _bar(_ts(0), 100.5, 100.6, 100.2, 100.3),
            _bar(_ts(1), 98.5, 98.7, 98.4, 98.6),       # fill at 98.5
            _bar(_ts(2), 98.6, 98.8, 98.1, 98.3),       # short of 97.00
            _bar(_ts(3), 98.3, 98.4, 96.9, 97.1),       # reaches 97.0
        ])
        out = resolve_leg('put', trigger_price=100.0, stop_price=101.0,
                          target_prices=[99.0, 98.5, 97.0], bars=bars)
        assert out.fill_price == pytest.approx(98.5)
        assert out.exit_reason == 't1'
        assert out.eod_pnl_pct == pytest.approx(round(1.5 / 98.5 * 100, 4))

    def test_no_bar_reaches_the_trigger_is_not_triggered(self):
        bars = _bars([_bar(_ts(0), 99.0, 99.5, 98.8, 99.2)])
        out = resolve_leg('call', trigger_price=100.0, stop_price=98.0,
                          target_prices=[101.0], bars=bars)
        assert out.entry_status == 'not_triggered'
        assert out.fill_price is None and out.eod_pnl_pct is None

    def test_missing_or_wrong_side_stop_is_invalid_stop(self):
        bars = _bars([
            _bar(_ts(0), 99.5, 100.2, 99.4, 100.0),
            _bar(_ts(1), 100.0, 101.5, 99.9, 101.2),
        ])
        for stop in (None, 100.5):
            out = resolve_leg('call', trigger_price=100.0, stop_price=stop,
                              target_prices=[101.0], bars=bars)
            assert out.entry_status == 'invalid_stop'
            assert out.exit_reason is None
            assert out.eod_pnl_pct is None and out.eod_pnl_dollar is None
            assert out.t1_hit_ts == bars.iloc[1]['time']


class _RecordingConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((getattr(sql, 'text', str(sql)), dict(params or {})))


class _RecordingEngine:
    def __init__(self):
        self.conn = _RecordingConn()

    def begin(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield self.conn
        return _cm()


def test_resolve_one_sets_and_binds_the_new_outcome_columns(monkeypatch):
    import gcp.premarket_playbook_resolver as mod

    row = pd.DataFrame([{
        'calls_trigger_price': 100.0, 'calls_stop_price': 99.0,
        'calls_t1_price': 101.0, 'calls_t2_price': 102.0, 'calls_t3_price': 103.0,
        'puts_trigger_price': 99.6, 'puts_stop_price': 100.5,
        'puts_t1_price': 99.0, 'puts_t2_price': 98.0, 'puts_t3_price': None,
        'outcome_resolved_at': None,
    }])
    # The session opens at 99.5, below the puts trigger 99.6: that leg is a
    # gap_through. Calls fill at 100.00 and exit at T1 101.00.
    bars = pd.DataFrame([
        {'time': _ts(0), 'open': 99.5, 'high': 100.2, 'low': 99.4, 'close': 100.0},
        {'time': _ts(1), 'open': 100.0, 'high': 101.3, 'low': 99.9, 'close': 101.2},
        {'time': _ts(2), 'open': 101.2, 'high': 101.4, 'low': 100.9, 'close': 101.0},
    ])
    reads = iter([row, bars])
    monkeypatch.setattr(mod.pd, 'read_sql', lambda *a, **k: next(reads))
    engine = _RecordingEngine()

    updates, reason = mod.resolve_one(_date(2026, 5, 6), 'spy', engine)

    assert reason == 'resolved'
    [(sql, bound)] = engine.conn.calls
    set_list = sql.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
    assigned = {part.split('=')[0].strip() for part in set_list.split(',')}
    for col in ('calls_entry_status', 'calls_fill_price', 'calls_exit_reason',
                'puts_entry_status', 'puts_fill_price', 'puts_exit_reason'):
        assert col in assigned
        assert f'{col} = :{col}' in set_list
    assert bound['calls_entry_status'] == 'filled'
    assert bound['calls_fill_price'] == pytest.approx(100.0)
    assert bound['calls_exit_reason'] == 't1'
    assert bound['calls_eod_pnl_pct'] == pytest.approx(1.0)
    assert bound['puts_entry_status'] == 'gap_through'
    assert bound['puts_fill_price'] is None
    assert bound['puts_exit_reason'] is None
    assert bound['puts_eod_pnl_pct'] is None
    assert bound['puts_eod_pnl_dollar'] is None
    assert bound['puts_trigger_hit_ts'] == pd.Timestamp(_ts(0))
    assert mod.RESOLVER_VERSION == '2026-11-16.v5'
    assert bound['outcome_resolver_version'] == '2026-11-16.v5'
    assert bound['d'] == '2026-05-06' and bound['t'] == 'SPY'


def test_schema_adds_the_traded_outcome_columns_nullable_without_default():
    import re
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / 'gcp' / 'schema.sql').read_text()
    for side in ('calls', 'puts'):
        for col, typ in (('entry_status', r'VARCHAR\(16\)'), ('fill_price', 'DOUBLE PRECISION'),
                         ('exit_reason', r'VARCHAR\(8\)')):
            assert re.search(rf'ADD COLUMN IF NOT EXISTS {side}_{col}\s+{typ}\s*,', sql), (side, col)


# ─── Exits in thirds, Design 6: the resolver scores the brief's plan ────
# docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md
# T0 is 09:30 ET, so _ts(29) is the 09:59 bar, _ts(30) the 10:00 bar and
# _ts(389) the 15:59 bar.

from gcp.premarket_playbook_resolver import PlanInputs, resolve_plan  # noqa: E402

CUTOFF_10_ET = 10 * 60
# The seeded policy's cutoff (drop-entry-cutoff spec, Design 1): 16:00 ET, the
# regular close, so every first cross in the session is an entry.
CUTOFF_SEEDED = 16 * 60


def _plan(**kw) -> PlanInputs:
    base = dict(trigger_price=100.0, stop_price=99.0, targets=(101.0, 102.0, 103.0),
                legs=3, cutoff_minutes=CUTOFF_10_ET, target_status='ok')
    base.update(kw)
    return PlanInputs(**base)


def _entered_at_0931(*later: dict) -> pd.DataFrame:
    """Opens below the 100.00 trigger and crosses it in the 09:31 bar
    (fill 100.00), then the given bars."""
    return _bars([
        _bar(_ts(0), 99.50, 99.80, 99.40, 99.70),
        _bar(_ts(1), 99.70, 100.20, 99.60, 100.10),
        *later,
    ])


class TestPlanOutcome:
    def test_an_open_through_the_trigger_is_not_an_entry(self):
        for open_ in (100.05, 100.00):
            bars = _bars([
                _bar(_ts(0), open_, 100.30, 99.90, 100.10),
                _bar(_ts(5), 100.10, 100.20, 100.00, 100.05),
                _bar(_ts(20), 100.05, 103.00, 100.00, 102.90),
                _bar(_ts(389), 102.90, 103.00, 102.40, 102.50),
            ])
            out = resolve_plan('call', _plan(), bars)
            assert out.entry_status == 'opened_through', open_
            assert out.r is None and out.r_status == 'not_entered'
            assert out.fill_price is None and out.exit is None

    def test_a_gap_fill_past_t1_and_t2_holds_every_leg_to_the_close(self):
        bars = _bars([
            _bar(_ts(0), 99.50, 99.80, 99.40, 99.70),
            _bar(_ts(10), 102.00, 103.20, 102.00, 102.60),   # 09:40, opens past the trigger
            _bar(_ts(11), 102.60, 102.90, 102.10, 102.50),
            _bar(_ts(200), 102.50, 102.80, 102.20, 102.40),
            _bar(_ts(389), 102.40, 102.70, 102.30, 102.50),  # 15:59 close 102.50
        ])
        out = resolve_plan('call', _plan(), bars)
        assert out.entry_status == 'entered'
        assert out.fill_price == pytest.approx(102.00)
        assert out.fill_ts == bars.iloc[1]['time']
        # T1 and T2 sit at or behind the fill and T3 is touched only on the
        # fill bar: no leg exits at a target.
        assert out.exit == 'close,close,close'
        assert out.r == pytest.approx(0.1667)
        booked_t1_t2 = round(((101.0 - 102.0) + (102.0 - 102.0) + 0.5) / 3 / 3.0, 4)
        assert out.r != pytest.approx(booked_t1_t2)

    def test_a_bar_opening_beyond_t3_books_t3_not_the_open(self):
        bars = _entered_at_0931(
            _bar(_ts(2), 103.40, 103.60, 103.30, 103.50),
            _bar(_ts(389), 103.50, 103.60, 103.40, 103.50),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.fill_price == pytest.approx(100.00)
        assert out.exit == 't1,t2,t3'
        assert out.r == pytest.approx(2.0)          # 103.40 would give 2.1333

    def test_the_cutoff_bar_is_late_and_the_bar_before_it_is_not(self):
        quiet = [_bar(_ts(m), 99.50, 99.80, 99.40, 99.70) for m in range(0, 29)]
        late = _bars(quiet + [_bar(_ts(29), 99.70, 99.90, 99.60, 99.80),
                              _bar(_ts(30), 99.80, 100.40, 99.70, 100.30),
                              _bar(_ts(389), 100.30, 100.50, 100.20, 100.40)])
        out = resolve_plan('call', _plan(), late)
        assert out.entry_status == 'late_cross' and out.r is None
        assert out.r_status == 'not_entered' and out.fill_price is None
        in_time = _bars(quiet + [_bar(_ts(29), 99.70, 100.40, 99.60, 100.30),
                                 _bar(_ts(389), 100.30, 100.50, 100.20, 100.40)])
        out = resolve_plan('call', _plan(), in_time)
        assert out.entry_status == 'entered'
        assert out.fill_price == pytest.approx(100.00)
        assert out.fill_ts == in_time.iloc[29]['time']

    def test_t1_t2_then_the_close(self):
        bars = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(9), 101.00, 102.20, 100.90, 102.10),
            _bar(_ts(389), 102.30, 102.60, 102.20, 102.50),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.exit == 't1,t2,close'
        assert out.r == pytest.approx(1.8333)       # a third each of 1, 2 and 2.5 R
        assert out.r_status == 'ok'

    def test_t1_then_the_stop(self):
        bars = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(9), 100.00, 100.10, 98.90, 99.00),
            _bar(_ts(389), 99.00, 99.20, 98.80, 99.10),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.exit == 't1,stop,stop'
        assert out.r == pytest.approx(-0.3333)

    def test_a_bar_touching_the_stop_and_a_target_counts_the_stop_first(self):
        bars = _entered_at_0931(
            _bar(_ts(2), 100.10, 101.20, 98.90, 100.00),
            _bar(_ts(389), 100.00, 100.20, 99.80, 100.00),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.exit == 'stop,stop,stop'
        assert out.r == pytest.approx(-1.0)

    def test_a_later_bar_opening_below_the_stop_exits_at_that_open(self):
        bars = _entered_at_0931(
            _bar(_ts(2), 98.50, 98.70, 98.40, 98.60),
            _bar(_ts(389), 98.60, 98.80, 98.50, 98.70),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.exit == 'stop,stop,stop'
        assert out.r == pytest.approx(-1.5)

    def test_one_target_gives_a_third_at_t1_and_two_thirds_to_the_stop_or_close(self):
        to_close = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(389), 102.30, 102.60, 102.20, 102.50),
        )
        out = resolve_plan('call', _plan(targets=(101.0,)), to_close)
        assert out.exit == 't1,close,close'
        assert out.r == pytest.approx(2.0)          # (1 + 2.5 + 2.5) / 3
        to_stop = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(9), 100.00, 100.10, 98.90, 99.00),
        )
        out = resolve_plan('call', _plan(targets=(101.0,)), to_stop)
        assert out.exit == 't1,stop,stop'
        assert out.r == pytest.approx(-0.3333)

    def test_a_put_side_mirrors_the_call(self):
        bars = _bars([
            _bar(_ts(0), 100.50, 100.60, 100.20, 100.30),
            _bar(_ts(1), 100.30, 100.40, 99.90, 99.95),     # crosses 100.00 down
            _bar(_ts(5), 99.60, 99.70, 98.90, 99.00),       # T1 99.00
            _bar(_ts(389), 98.60, 98.70, 98.40, 98.50),
        ])
        out = resolve_plan('put', _plan(stop_price=101.0, targets=(99.0, 98.0, 97.0)), bars)
        assert out.entry_status == 'entered' and out.fill_price == pytest.approx(100.0)
        assert out.exit == 't1,close,close'
        assert out.r == pytest.approx(round((1.0 + 1.5 + 1.5) / 3, 4))

    def test_no_stop_keeps_the_exits_with_no_r_and_main_s_existing_columns(self):
        # The state test_no_stop_when_no_fresh_opposite builds: a trigger and
        # targets, stop None.
        bars = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(9), 101.00, 102.20, 100.90, 102.10),
            _bar(_ts(389), 102.30, 102.60, 102.20, 102.50),
        )
        out = resolve_plan('call', _plan(stop_price=None), bars)
        assert out.entry_status == 'entered'
        assert out.r is None and out.r_status == 'stop_unavailable'
        assert out.exit == 't1,t2,close'
        leg = resolve_leg('call', trigger_price=100.0, stop_price=None,
                          target_prices=[101.0, 102.0, 103.0], bars=bars)
        assert leg.entry_status == 'invalid_stop'
        assert leg.trigger_hit_ts == bars.iloc[1]['time']
        assert leg.t1_hit_ts == bars.iloc[2]['time'] and leg.t2_hit_ts == bars.iloc[3]['time']
        assert leg.t3_hit_ts is None and leg.stop_hit_ts is None
        assert leg.mfe_pct == pytest.approx(2.6) and leg.mae_pct == pytest.approx(0.4)
        assert leg.eod_pnl_pct is None and leg.eod_pnl_dollar is None

    def test_targets_unavailable_is_not_scored_and_no_target_is_a_valid_plan(self):
        quiet = [_bar(_ts(m), 99.50, 99.80, 99.40, 99.70) for m in range(0, 29)]
        bars = _bars(quiet + [_bar(_ts(29), 99.70, 100.40, 99.60, 100.30),
                              _bar(_ts(389), 102.30, 102.60, 102.20, 102.50)])
        out = resolve_plan('call', _plan(targets=(), target_status='params_unavailable'), bars)
        assert out.entry_status == 'entered' and out.fill_price == pytest.approx(100.0)
        assert out.fill_ts == bars.iloc[29]['time']
        assert out.r is None and out.exit is None and out.r_status == 'targets_unavailable'
        assert (out.t1_hit_ts, out.t2_hit_ts, out.t3_hit_ts) == (None, None, None)
        out = resolve_plan('call', _plan(targets=()), bars)
        assert out.r == pytest.approx(2.5)
        assert out.exit == 'close,close,close' and out.r_status == 'ok'

    def test_plan_hit_timestamps_follow_the_plan_targets(self):
        bars = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.00, 100.30, 100.90),
            _bar(_ts(389), 100.90, 100.95, 100.60, 100.80),
        )
        out = resolve_plan('call', _plan(), bars)
        assert out.t1_hit_ts == bars.iloc[2]['time']
        assert out.t2_hit_ts is None and out.t3_hit_ts is None
        leg = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[100.5, 101.0, 101.5], bars=bars)
        assert leg.t1_hit_ts == bars.iloc[2]['time'] and leg.t2_hit_ts == bars.iloc[2]['time']
        assert leg.t3_hit_ts is None

    def test_the_existing_outcome_is_unchanged_by_the_plan(self):
        # The cross-fill-t1-v1 columns for the same bars are computed by
        # resolve_leg alone; the plan never feeds them.
        bars = _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(389), 102.30, 102.60, 102.20, 102.50),
        )
        leg = resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                          target_prices=[101.0, 102.0, 103.0], bars=bars)
        assert leg.entry_status == 'filled' and leg.exit_reason == 't1'
        assert leg.eod_pnl_pct == pytest.approx(1.0)
        assert leg.trigger_hit_ts == bars.iloc[1]['time'] and leg.t1_hit_ts == bars.iloc[2]['time']
        assert leg.t2_hit_ts == bars.iloc[3]['time'] and leg.stop_hit_ts is None

    def test_resolver_version_moves_past_the_scorer_spec(self):
        import gcp.premarket_playbook_resolver as mod
        assert mod.RESOLVER_VERSION != '2026-11-11.v2'
        assert mod.RESOLVER_VERSION > '2026-11-11.v2'


class TestPlanInputs:
    def test_a_v3_basis_is_the_source(self):
        import gcp.premarket_playbook_resolver as mod
        from tests.lib.session_levels_helpers import d8_basis

        basis = d8_basis()
        calls = mod.plan_inputs('calls', {}, basis, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.trigger_price == pytest.approx(252.10)
        assert calls.stop_price == pytest.approx(248.20)
        assert calls.targets == pytest.approx((275.00, 280.00, 285.00))
        assert calls.legs == 3 and calls.cutoff_minutes == CUTOFF_SEEDED
        assert calls.target_status == 'ok' and calls.plan_available
        puts = mod.plan_inputs('puts', {}, basis, policy_fn=lambda: pytest.fail('no policy read'))
        assert puts.trigger_price == pytest.approx(248.20)
        assert puts.targets == pytest.approx((225.00, 220.00, 215.00))

    def test_a_spacing_not_ok_publishes_no_plan(self):
        import gcp.premarket_playbook_resolver as mod
        from tests.lib.session_levels_helpers import d8_basis

        basis = d8_basis(statuses={'target_min_spacing_atr': 'params_unavailable'})
        calls = mod.plan_inputs('calls', {}, basis, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.target_status == 'params_unavailable' and not calls.plan_available
        assert calls.trigger_price == pytest.approx(252.10)

    def test_an_entry_cutoff_not_ok_publishes_no_plan_and_scores_none(self):
        """The brief prints no plan when the cutoff is not ok, and the
        resolver scores none: targets_unavailable, never an all-close trade
        with no cutoff (Codex P1 on #1832)."""
        import gcp.premarket_playbook_resolver as mod
        from tests.lib.session_levels_helpers import d8_basis

        basis = d8_basis(statuses={'entry_cutoff_et': 'input_unavailable'})
        calls = mod.plan_inputs('calls', {}, basis, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.target_status == 'input_unavailable' and not calls.plan_available
        assert calls.targets == () and calls.cutoff_minutes is None
        assert calls.trigger_price == pytest.approx(252.10)
        assert calls.stop_price == pytest.approx(248.20)
        quiet = [_bar(_ts(m), 251.50, 251.90, 251.40, 251.80) for m in range(0, 29)]
        bars = _bars(quiet + [_bar(_ts(29), 251.80, 252.40, 251.70, 252.30),
                              _bar(_ts(389), 254.00, 254.20, 253.90, 254.10)])
        out = resolve_plan('call', calls, bars)
        assert out.r is None and out.exit is None and out.r_status == 'targets_unavailable'
        assert (out.t1_hit_ts, out.t2_hit_ts, out.t3_hit_ts) == (None, None, None)

    def test_a_v2_basis_falls_back_to_the_structured_columns_and_the_policy(self):
        import gcp.premarket_playbook_resolver as mod
        from lib.strat_levels import LEVEL_RULE_V2
        from tests.lib.level_params_fixtures import fixture_params
        from tests.lib.session_levels_helpers import d8_basis

        basis = {**d8_basis(), 'rule_version': LEVEL_RULE_V2}
        row = {'calls_trigger_price': 252.10, 'calls_stop_price': 248.20,
               'calls_t1_price': 253.00, 'calls_t2_price': 275.00, 'calls_t3_price': None}
        calls = mod.plan_inputs('calls', row, basis, policy_fn=lambda: fixture_params('TST'))
        assert calls.targets == pytest.approx((253.00, 275.00))
        assert calls.legs == 3 and calls.cutoff_minutes == CUTOFF_SEEDED
        assert calls.plan_available

    @pytest.mark.parametrize('rule_version', ['feat-strat-001.v1', None])
    def test_a_basis_other_than_v2_or_v3_has_no_plan(self, rule_version):
        import gcp.premarket_playbook_resolver as mod
        from tests.lib.session_levels_helpers import d8_basis

        basis = {k: v for k, v in d8_basis().items() if k != 'rule_version'}
        if rule_version is not None:
            basis['rule_version'] = rule_version
        row = {'calls_trigger_price': 252.10, 'calls_stop_price': 248.20,
               'calls_t1_price': 253.00, 'calls_t2_price': 275.00, 'calls_t3_price': None}
        calls = mod.plan_inputs('calls', row, basis, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.target_status == 'targets_unavailable' and not calls.plan_available
        assert calls.targets == () and calls.legs is None

    def test_a_row_without_level_basis_has_no_plan(self):
        import gcp.premarket_playbook_resolver as mod

        row = {'calls_trigger_price': 100.0, 'calls_stop_price': 99.0}
        calls = mod.plan_inputs('calls', row, None, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.target_status == 'targets_unavailable' and not calls.plan_available


def _plan_set_and_bound(engine):
    # The premarket_analysis UPDATE is the first statement; a resolved trade
    # is followed by its plan_excursions write (target hit rates spec).
    (sql, bound), *rest = engine.conn.calls
    assert sql.startswith('UPDATE premarket_analysis SET ')
    assert all('plan_excursions' in later for later, _ in rest) and len(rest) <= 1
    set_list = sql.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
    return set_list, bound


PLAN_FIELDS = ('entry_status', 'fill_price', 'fill_ts', 'r', 'r_status',
               't1_hit_ts', 't2_hit_ts', 't3_hit_ts', 'exit')


def test_resolve_one_binds_the_plan_columns_from_a_v3_basis(monkeypatch):
    import json

    import gcp.premarket_playbook_resolver as mod
    from tests.lib.session_levels_helpers import d8_basis

    row = pd.DataFrame([{
        'calls_trigger_price': 252.10, 'calls_stop_price': 248.20,
        'calls_t1_price': 253.00, 'calls_t2_price': 275.00, 'calls_t3_price': 280.00,
        'puts_trigger_price': 248.20, 'puts_stop_price': 252.10,
        'puts_t1_price': 247.50, 'puts_t2_price': 247.00, 'puts_t3_price': 225.00,
        'level_basis': json.dumps(d8_basis()), 'outcome_resolved_at': None,
    }])
    bars = pd.DataFrame([
        {'time': _ts(0), 'open': 251.00, 'high': 251.50, 'low': 250.80, 'close': 251.40},
        {'time': _ts(1), 'open': 251.90, 'high': 252.50, 'low': 251.80, 'close': 252.40},
        {'time': _ts(2), 'open': 260.00, 'high': 276.00, 'low': 259.00, 'close': 270.00},
        {'time': _ts(389), 'open': 270.00, 'high': 271.00, 'low': 269.00, 'close': 270.00},
    ])
    reads = iter([row, bars])
    monkeypatch.setattr(mod.pd, 'read_sql', lambda *a, **k: next(reads))
    engine = _RecordingEngine()

    updates, reason = mod.resolve_one(_date(2026, 5, 6), 'tst', engine)

    assert reason == 'resolved'
    set_list, bound = _plan_set_and_bound(engine)
    for side in ('calls', 'puts'):
        for f in PLAN_FIELDS:
            assert f'{side}_plan_{f} = :{side}_plan_{f}' in set_list
            assert f'{side}_plan_{f}' in bound
    assert bound['calls_plan_entry_status'] == 'entered'
    assert bound['calls_plan_fill_price'] == pytest.approx(252.10)
    assert bound['calls_plan_fill_ts'] == pd.Timestamp(_ts(1))
    assert bound['calls_plan_exit'] == 't1,close,close'
    assert bound['calls_plan_r'] == pytest.approx(round((22.9 + 2 * 17.9) / 3 / 3.9, 4))
    assert bound['calls_plan_r_status'] == 'ok'
    assert bound['calls_plan_t1_hit_ts'] == pd.Timestamp(_ts(2))
    assert bound['calls_plan_t2_hit_ts'] is None and bound['calls_plan_t3_hit_ts'] is None
    # The existing columns keep the gating targets and rule cross-fill-t1-v1.
    assert bound['calls_t1_hit_ts'] == pd.Timestamp(_ts(2))
    assert bound['calls_exit_reason'] == 't1'
    assert bound['puts_plan_entry_status'] == 'no_cross'
    assert bound['puts_plan_r'] is None and bound['puts_plan_r_status'] == 'not_entered'
    assert bound['outcome_resolver_version'] == mod.RESOLVER_VERSION != '2026-11-11.v2'


def test_resolve_one_binds_a_targets_unavailable_leg_and_a_stop_unavailable_leg(monkeypatch):
    import gcp.premarket_playbook_resolver as mod

    row = pd.DataFrame([{
        'calls_trigger_price': 100.0, 'calls_stop_price': None,
        'calls_t1_price': 101.0, 'calls_t2_price': 102.0, 'calls_t3_price': 103.0,
        'puts_trigger_price': 99.6, 'puts_stop_price': 100.5,
        'puts_t1_price': 99.0, 'puts_t2_price': 98.0, 'puts_t3_price': None,
        'level_basis': None, 'outcome_resolved_at': None,
    }])
    bars = pd.DataFrame([
        {'time': _ts(0), 'open': 99.90, 'high': 100.00, 'low': 99.70, 'close': 99.95},
        {'time': _ts(1), 'open': 99.95, 'high': 101.20, 'low': 99.50, 'close': 101.00},
        {'time': _ts(389), 'open': 102.40, 'high': 102.60, 'low': 102.30, 'close': 102.50},
    ])
    plans = {
        'calls': _plan(stop_price=None),
        'puts': _plan(trigger_price=99.6, stop_price=100.5, targets=(),
                      target_status='params_unavailable'),
    }
    monkeypatch.setattr(mod, 'plan_inputs', lambda side, *a, **k: plans[side])
    reads = iter([row, bars])
    monkeypatch.setattr(mod.pd, 'read_sql', lambda *a, **k: next(reads))
    engine = _RecordingEngine()

    mod.resolve_one(_date(2026, 5, 6), 'spy', engine)

    _, bound = _plan_set_and_bound(engine)
    assert bound['calls_plan_r_status'] == 'stop_unavailable'
    assert bound['calls_plan_r'] is None
    assert bound['calls_plan_exit'] == 't1,t2,close'
    assert bound['calls_entry_status'] == 'invalid_stop' and bound['calls_eod_pnl_pct'] is None
    assert bound['puts_plan_r_status'] == 'targets_unavailable'
    assert bound['puts_plan_entry_status'] == 'entered'
    assert bound['puts_plan_fill_price'] == pytest.approx(99.6)
    assert bound['puts_plan_r'] is None and bound['puts_plan_exit'] is None
    for k in (1, 2, 3):
        assert bound[f'puts_plan_t{k}_hit_ts'] is None


def test_schema_adds_the_plan_columns_nullable_without_default():
    import re
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / 'gcp' / 'schema.sql').read_text()
    for side in ('calls', 'puts'):
        for col, typ in (('entry_status', r'VARCHAR\(16\)'), ('fill_price', 'DOUBLE PRECISION'),
                         ('fill_ts', 'TIMESTAMPTZ'), ('r', 'DOUBLE PRECISION'),
                         ('r_status', r'VARCHAR\(24\)'), ('t1_hit_ts', 'TIMESTAMPTZ'),
                         ('t2_hit_ts', 'TIMESTAMPTZ'), ('t3_hit_ts', 'TIMESTAMPTZ'),
                         ('exit', 'TEXT')):
            assert re.search(rf'ADD COLUMN IF NOT EXISTS {side}_plan_{col}\s+{typ}\s*,', sql), (side, col)


# ─── Drop the entry cutoff (2026-11-15) ─────────────────────────────────
# docs/superpowers/specs/2026-11-15-feat-strat-001-drop-entry-cutoff.md


class TestSeededCutoff:
    """The plan built from a v2 row and the policy seeded in gcp/schema.sql
    takes a first cross anywhere in the regular session."""

    @staticmethod
    def _inputs():
        import gcp.premarket_playbook_resolver as mod
        from lib.strat_levels import LEVEL_RULE_V2
        from tests.lib.level_params_fixtures import fixture_params
        from tests.lib.session_levels_helpers import d8_basis

        basis = {**d8_basis(), 'rule_version': LEVEL_RULE_V2}
        row = {'calls_trigger_price': 100.00, 'calls_stop_price': 99.00,
               'calls_t1_price': 101.00, 'calls_t2_price': 102.00, 'calls_t3_price': 103.00}
        return mod.plan_inputs('calls', row, basis, policy_fn=lambda: fixture_params('TST'))

    @pytest.mark.parametrize('cross_minute', [30, 389])   # the 10:00 and 15:59 bars
    def test_a_first_cross_after_10_is_an_entry(self, cross_minute):
        plan = self._inputs()
        assert plan.cutoff_minutes == CUTOFF_SEEDED and plan.plan_available
        quiet = [_bar(_ts(m), 99.50, 99.80, 99.40, 99.70) for m in range(0, cross_minute)]
        bars = _bars(quiet + [_bar(_ts(cross_minute), 99.70, 100.20, 99.60, 100.10)])
        out = resolve_plan('call', plan, bars)
        assert out.entry_status == 'entered', cross_minute
        assert out.fill_price == pytest.approx(100.00)
        assert out.fill_ts == bars.iloc[-1]['time']


# 2026-11-27 is a half day: 09:30 ET is 14:30 UTC and the close is 13:00 ET
# (18:00 UTC), from the NYSE calendar.
HALF_DAY = datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc)


def _hd(minute_offset: int) -> datetime:
    return HALF_DAY + timedelta(minutes=minute_offset)


def _half_day_row():
    return pd.DataFrame([{
        'calls_trigger_price': 100.0, 'calls_stop_price': 99.0,
        'calls_t1_price': 101.0, 'calls_t2_price': 102.0, 'calls_t3_price': 103.0,
        'puts_trigger_price': 95.0, 'puts_stop_price': 96.0,
        'puts_t1_price': 94.0, 'puts_t2_price': 93.0, 'puts_t3_price': 92.0,
        'level_basis': None, 'outcome_resolved_at': None,
    }])


def _resolve_half_day(monkeypatch, bars):
    """resolve_one on the half day with the seeded cutoff, reading `bars` as
    the 09:30 to 15:59 ET query returns them."""
    import gcp.premarket_playbook_resolver as mod

    plans = {'calls': _plan(cutoff_minutes=CUTOFF_SEEDED),
             'puts': _plan(trigger_price=95.0, stop_price=96.0, targets=(94.0, 93.0, 92.0),
                           cutoff_minutes=CUTOFF_SEEDED)}
    monkeypatch.setattr(mod, 'plan_inputs', lambda side, *a, **k: plans[side])
    reads = iter([_half_day_row(), bars])
    monkeypatch.setattr(mod.pd, 'read_sql', lambda *a, **k: next(reads))
    engine = _RecordingEngine()
    updates, reason = mod.resolve_one(_date(2026, 11, 27), 'tst', engine)
    assert reason == 'resolved'
    return mod, _plan_set_and_bound(engine)[1]


def test_a_cross_after_a_half_day_close_is_no_plan_entry(monkeypatch):
    bars = pd.DataFrame([
        {'time': _hd(0), 'open': 99.50, 'high': 99.80, 'low': 99.40, 'close': 99.70},
        {'time': _hd(209), 'open': 99.70, 'high': 99.80, 'low': 99.60, 'close': 99.75},  # 12:59
        {'time': _hd(240), 'open': 99.75, 'high': 100.40, 'low': 99.70, 'close': 100.30},  # 13:30
    ])
    mod, bound = _resolve_half_day(monkeypatch, bars)
    assert bound['calls_plan_entry_status'] == 'no_cross'
    assert bound['calls_plan_r'] is None and bound['calls_plan_fill_price'] is None
    # The existing columns read every bar to 15:59, as on origin/main.
    want = mod.resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                           target_prices=[101.0, 102.0, 103.0],
                           bars=bars.assign(time=pd.to_datetime(bars['time'], utc=True)))
    assert bound['calls_trigger_hit_ts'] == want.trigger_hit_ts == pd.Timestamp(_hd(240))
    assert bound['calls_eod_pnl_pct'] == want.eod_pnl_pct
    assert bound['outcome_resolver_version'] == mod.RESOLVER_VERSION


def test_a_half_day_close_leg_books_the_last_bar_before_the_close(monkeypatch):
    bars = pd.DataFrame([
        {'time': _hd(0), 'open': 99.50, 'high': 99.80, 'low': 99.40, 'close': 99.70},
        {'time': _hd(15), 'open': 99.70, 'high': 100.20, 'low': 99.60, 'close': 100.10},  # 09:45
        {'time': _hd(209), 'open': 100.40, 'high': 100.60, 'low': 100.30, 'close': 100.50},  # 12:59
        {'time': _hd(240), 'open': 100.70, 'high': 100.90, 'low': 100.60, 'close': 100.80},  # 13:30
    ])
    mod, bound = _resolve_half_day(monkeypatch, bars)
    assert bound['calls_plan_entry_status'] == 'entered'
    assert bound['calls_plan_fill_ts'] == pd.Timestamp(_hd(15))
    assert bound['calls_plan_exit'] == 'close,close,close'
    assert bound['calls_plan_r'] == pytest.approx(0.5)     # 100.50, not the 13:30 print's 0.8
    want = mod.resolve_leg('call', trigger_price=100.0, stop_price=99.0,
                           target_prices=[101.0, 102.0, 103.0],
                           bars=bars.assign(time=pd.to_datetime(bars['time'], utc=True)))
    for col in ('trigger_hit_ts', 't1_hit_ts', 't2_hit_ts', 't3_hit_ts', 'stop_hit_ts',
                'eod_pnl_pct', 'exit_reason', 'fill_price'):
        assert bound[f'calls_{col}'] == getattr(want, col), col
    assert bound['calls_eod_pnl_pct'] == pytest.approx(0.8)


# ─── Target hit rates spec (2026-11-16), Design 3: the excursion ───────────

from gcp.premarket_playbook_resolver import (  # noqa: E402
    ExcursionResult, plan_excursion, trade_of_day,
)


def _puts_plan(**kw) -> PlanInputs:
    base = dict(trigger_price=100.0, stop_price=101.0, targets=(99.0, 98.0, 97.0),
                legs=3, cutoff_minutes=CUTOFF_SEEDED, target_status='ok')
    base.update(kw)
    return PlanInputs(**base)


def _calls_plan(**kw) -> PlanInputs:
    return _plan(**{'cutoff_minutes': CUTOFF_SEEDED, **kw})


def _puts_entered_at_0931(*later: dict) -> pd.DataFrame:
    """Opens above the 100.00 puts trigger and crosses it in the 09:31 bar."""
    return _bars([
        _bar(_ts(0), 100.50, 100.60, 100.20, 100.30),
        _bar(_ts(1), 100.30, 100.40, 99.80, 99.90),
        *later,
    ])


def _gap_fill_calls() -> pd.DataFrame:
    """done_when[2]'s gap fixture: trigger 100, stop 99, the cross bar opens
    at 102 (fill 102.00) and a later high is 102.90."""
    return _bars([
        _bar(_ts(0), 99.50, 99.80, 99.40, 99.70),
        _bar(_ts(10), 102.00, 103.20, 102.00, 102.60),
        _bar(_ts(11), 102.60, 102.90, 102.10, 102.50),
        _bar(_ts(200), 102.50, 102.80, 102.20, 102.40),
        _bar(_ts(389), 102.40, 102.70, 102.30, 102.50),
    ])


# (direction, plan, bars, excursion_r, excursion_held5_r) on hand-built days.
EXCURSION_FIXTURES = {
    'calls_rung_only_on_the_fill_bar': (
        'call', _calls_plan(), _bars([
            _bar(_ts(0), 99.50, 99.80, 99.40, 99.70),
            _bar(_ts(1), 99.70, 101.50, 99.60, 100.10),     # fill bar touches 101
            _bar(_ts(2), 100.10, 100.40, 99.90, 100.20),
            _bar(_ts(389), 100.20, 100.30, 100.00, 100.10),
        ]), 0.40, None),
    'calls_stop_and_rung_on_one_bar': (
        'call', _calls_plan(), _entered_at_0931(
            _bar(_ts(2), 100.10, 100.50, 100.00, 100.30),
            _bar(_ts(3), 100.30, 101.20, 98.90, 99.00),     # stop and 101 together
            _bar(_ts(389), 99.00, 102.50, 98.80, 102.00),
        ), 0.50, None),
    'calls_nothing_between_fill_and_stop': (
        'call', _calls_plan(), _entered_at_0931(
            _bar(_ts(2), 100.00, 101.50, 98.90, 99.00),
            _bar(_ts(389), 99.00, 103.50, 98.80, 103.00),
        ), None, None),
    'calls_five_closes_ending_on_the_stop_bar': (
        'call', _calls_plan(), _entered_at_0931(
            _bar(_ts(2), 100.10, 101.20, 100.00, 101.10),
            _bar(_ts(3), 101.10, 101.30, 101.00, 101.10),
            _bar(_ts(4), 101.10, 101.30, 101.00, 101.10),
            _bar(_ts(5), 101.10, 101.30, 101.00, 101.10),
            _bar(_ts(6), 101.10, 101.20, 98.90, 101.10),    # stop bar, 5th close
            _bar(_ts(389), 99.00, 99.20, 98.80, 99.10),
        ), 1.30, None),
    'calls_five_closes_held': (
        'call', _calls_plan(), _entered_at_0931(
            _bar(_ts(2), 100.10, 101.20, 100.00, 101.10),
            _bar(_ts(3), 101.10, 101.30, 101.00, 101.20),
            _bar(_ts(4), 101.10, 101.30, 101.00, 101.30),
            _bar(_ts(5), 101.10, 101.40, 101.00, 101.15),
            _bar(_ts(6), 101.10, 101.30, 101.00, 101.25),
            _bar(_ts(389), 101.20, 101.30, 101.00, 101.20),
        ), 1.40, 1.15),
    'calls_gap_fill': ('call', _calls_plan(), _gap_fill_calls(), 2.90, None),
    'calls_t1_t2_then_the_close': (
        'call', _calls_plan(), _entered_at_0931(
            _bar(_ts(5), 100.40, 101.10, 100.30, 101.00),
            _bar(_ts(9), 101.00, 102.20, 100.90, 102.10),
            _bar(_ts(389), 102.30, 102.60, 102.20, 102.50),
        ), 2.60, None),
    'puts_t1_then_the_stop': (
        'put', _puts_plan(), _puts_entered_at_0931(
            _bar(_ts(5), 99.60, 99.70, 98.90, 99.00),
            _bar(_ts(9), 99.00, 101.10, 98.80, 101.00),     # stop and 98.80 together
            _bar(_ts(389), 101.00, 101.20, 96.00, 96.50),
        ), 1.10, None),
    'puts_stop_and_rung_on_one_bar': (
        'put', _puts_plan(), _puts_entered_at_0931(
            _bar(_ts(2), 99.90, 101.10, 98.90, 100.50),
            _bar(_ts(389), 100.50, 100.60, 96.00, 96.50),
        ), None, None),
    'puts_gap_fill': (
        'put', _puts_plan(), _bars([
            _bar(_ts(0), 100.50, 100.60, 100.20, 100.30),
            _bar(_ts(10), 98.00, 98.00, 96.80, 97.40),      # opens beyond the trigger
            _bar(_ts(11), 97.40, 97.90, 97.10, 97.50),
            _bar(_ts(389), 97.50, 97.80, 97.30, 97.60),
        ]), 2.90, None),
}


class TestPlanExcursion:
    @pytest.mark.parametrize('name', sorted(EXCURSION_FIXTURES))
    def test_each_fixture_gives_its_excursion(self, name):
        direction, plan, bars, want, want_held = EXCURSION_FIXTURES[name]
        got = plan_excursion(direction, plan, bars)
        assert got is not None
        assert got.excursion_r == (pytest.approx(want) if want is not None else None)
        assert got.excursion_held5_r == (pytest.approx(want_held) if want_held is not None else None)

    def test_a_rung_touched_only_on_the_fill_bar_is_not_reached(self):
        _, plan, bars, _, _ = EXCURSION_FIXTURES['calls_rung_only_on_the_fill_bar']
        assert not plan_excursion('call', plan, bars).excursion_r >= 1.0

    def test_a_bar_touching_the_stop_and_a_rung_counts_the_stop_first(self):
        for name, rung in (('calls_stop_and_rung_on_one_bar', 1.0),
                           ('puts_stop_and_rung_on_one_bar', 1.0)):
            d, plan, bars, _, _ = EXCURSION_FIXTURES[name]
            got = plan_excursion(d, plan, bars)
            assert got.stop_i is not None
            assert got.excursion_r is None or got.excursion_r < rung, name

    def test_no_bar_between_the_fill_bar_and_the_stop_bar_gives_none(self):
        _, plan, bars, _, _ = EXCURSION_FIXTURES['calls_nothing_between_fill_and_stop']
        got = plan_excursion('call', plan, bars)
        assert got.stop_i == got.fill_i + 1
        assert got.excursion_r is None and got.excursion_held5_r is None

    def test_five_closes_ending_on_the_stop_bar_are_not_held(self):
        _, plan, bars, _, _ = EXCURSION_FIXTURES['calls_five_closes_ending_on_the_stop_bar']
        got = plan_excursion('call', plan, bars)
        assert got.excursion_held5_r is None
        _, plan, bars, _, _ = EXCURSION_FIXTURES['calls_five_closes_held']
        assert plan_excursion('call', plan, bars).excursion_held5_r == pytest.approx(1.15)

    def test_a_cross_bar_that_opened_beyond_the_trigger_is_measured_from_the_trigger(self):
        """done_when[2]'s gap fixture: excursion 2.9, rungs 101 and 102
        reached (at or behind the 102.00 fill), 103 not."""
        got = plan_excursion('call', _calls_plan(), _gap_fill_calls())
        assert got.fill_price == pytest.approx(102.00)
        assert got.excursion_r == pytest.approx(2.9)
        reached = [p for p in (101.0, 102.0, 103.0) if got.excursion_r >= (p - 100.0) / 1.0]
        assert reached == [101.0, 102.0]
        got = plan_excursion('put', _puts_plan(), EXCURSION_FIXTURES['puts_gap_fill'][2])
        assert got.fill_price == pytest.approx(98.00)
        assert got.excursion_r == pytest.approx(2.9)

    @pytest.mark.parametrize('name', sorted(EXCURSION_FIXTURES))
    def test_a_rung_beyond_the_fill_is_reached_exactly_when_the_exit_walk_sells_there(self, name):
        direction, plan, bars, _, _ = EXCURSION_FIXTURES[name]
        got = plan_excursion(direction, plan, bars)
        out = resolve_plan(direction, plan, bars)
        sign = 1 if direction == 'call' else -1
        risk = abs(plan.trigger_price - plan.stop_price)
        for k, t in enumerate(plan.targets):
            if sign * (t - out.fill_price) <= 0:
                continue                         # at or behind the fill: held by resolve_plan
            d = sign * (t - plan.trigger_price) / risk
            reached = got.excursion_r is not None and got.excursion_r >= d - 1e-9
            assert reached == (out.exit.split(',')[k] == f't{k + 1}'), (name, t)

    def test_not_entered_or_no_valid_stop_gives_none(self):
        bars = _bars([_bar(_ts(0), 100.05, 100.30, 99.90, 100.10),
                      _bar(_ts(389), 100.10, 103.00, 100.00, 102.90)])
        assert plan_excursion('call', _calls_plan(), bars) is None          # opened through
        bars = _entered_at_0931(_bar(_ts(389), 100.10, 101.50, 100.00, 101.00))
        assert plan_excursion('call', _calls_plan(stop_price=None), bars) is None
        assert plan_excursion('call', _calls_plan(stop_price=100.5), bars) is None
        assert plan_excursion('call', _calls_plan(cutoff_minutes=None), bars) is None
        assert plan_excursion('call', _calls_plan(trigger_price=None), bars) is None
        assert plan_excursion('call', _calls_plan(), bars.iloc[0:0]) is None


class TestTradeOfDay:
    @staticmethod
    def _r(i):
        return ExcursionResult(fill_i=i, fill_price=100.0, fill_ts=None, stop_i=None,
                               stop_ts=None, excursion_r=1.0, excursion_held5_r=None)

    def test_calls_only(self):
        c = self._r(3)
        assert trade_of_day(c, None) == ('calls', c)

    def test_puts_only(self):
        p = self._r(3)
        assert trade_of_day(None, p) == ('puts', p)

    def test_both_keeps_the_earlier_fill(self):
        c, p = self._r(2), self._r(5)
        assert trade_of_day(c, p) == ('calls', c)
        assert trade_of_day(self._r(7), p) == ('puts', p)

    def test_a_same_bar_tie_or_neither_gives_no_trade(self):
        assert trade_of_day(self._r(4), self._r(4)) is None
        assert trade_of_day(None, None) is None



# ─── Target hit rates spec, Design 4: resolve_one writes the day's trade ──

def _v3_row():
    import json

    from tests.lib.session_levels_helpers import d8_basis
    return pd.DataFrame([{
        'calls_trigger_price': 252.10, 'calls_stop_price': 248.20,
        'calls_t1_price': 253.00, 'calls_t2_price': 275.00, 'calls_t3_price': 280.00,
        'puts_trigger_price': 248.20, 'puts_stop_price': 252.10,
        'puts_t1_price': 247.50, 'puts_t2_price': 247.00, 'puts_t3_price': 225.00,
        'level_basis': json.dumps(d8_basis()), 'outcome_resolved_at': None,
    }])


_CALLS_TRADE_BARS = [
    {'time': _ts(0), 'open': 251.00, 'high': 251.50, 'low': 250.80, 'close': 251.40},
    {'time': _ts(1), 'open': 251.90, 'high': 252.50, 'low': 251.80, 'close': 252.40},
    {'time': _ts(2), 'open': 260.00, 'high': 276.00, 'low': 259.00, 'close': 270.00},
    {'time': _ts(389), 'open': 270.00, 'high': 271.00, 'low': 269.00, 'close': 270.00},
]
# Opens through the calls trigger (252.10) and never reaches the puts
# trigger (248.20): no side enters, no trade.
_NO_TRADE_BARS = [
    {'time': _ts(0), 'open': 252.50, 'high': 253.00, 'low': 252.20, 'close': 252.80},
    {'time': _ts(389), 'open': 252.80, 'high': 253.10, 'low': 252.30, 'close': 252.90},
]


def _resolve(monkeypatch, row, bars, force=False):
    import gcp.premarket_playbook_resolver as mod

    reads = iter([row, pd.DataFrame(bars)])
    monkeypatch.setattr(mod.pd, 'read_sql', lambda *a, **k: next(reads))
    engine = _RecordingEngine()
    updates, reason = mod.resolve_one(_date(2026, 5, 6), 'tst', engine, force=force)
    assert reason == 'resolved'
    return updates, engine.conn.calls


def test_resolve_one_upserts_the_day_s_trade_in_the_same_transaction(monkeypatch):
    import gcp.premarket_playbook_resolver as mod
    from lib.strat_levels import LEVEL_RULE_VERSION

    _, calls = _resolve(monkeypatch, _v3_row(), _CALLS_TRADE_BARS)
    assert len(calls) == 2
    assert calls[0][0].startswith('UPDATE premarket_analysis SET ')
    sql, bound = calls[1]
    assert sql.startswith('INSERT INTO plan_excursions ')
    assert 'ON CONFLICT (ticker, session_date, rule_version) DO UPDATE SET' in sql
    assert "plan_excursions.source = 'history'" not in sql
    assert (bound['t'], bound['d'], bound['v']) == ('TST', '2026-05-06', LEVEL_RULE_VERSION)
    assert (bound['side'], bound['source'], bound['rv']) == ('calls', 'resolver', mod.RESOLVER_VERSION)
    assert (bound['trigger'], bound['stop'], bound['fill']) == (252.10, 248.20, pytest.approx(252.10))
    assert bound['fill_ts'] == pd.Timestamp(_ts(1)) and bound['stop_ts'] is None
    assert bound['xr'] == pytest.approx((276.00 - 252.10) / 3.9)
    assert bound['xh'] is None


def test_a_forced_re_resolution_to_no_trade_deletes_the_day_s_row(monkeypatch):
    from lib.strat_levels import LEVEL_RULE_VERSION

    _, first = _resolve(monkeypatch, _v3_row(), _CALLS_TRADE_BARS)
    assert first[1][0].startswith('INSERT INTO plan_excursions ')
    row = _v3_row()
    row.loc[0, 'outcome_resolved_at'] = pd.Timestamp('2026-05-06T21:00:00Z')
    _, calls = _resolve(monkeypatch, row, _NO_TRADE_BARS, force=True)
    assert len(calls) == 2
    sql, bound = calls[1]
    assert sql == ('DELETE FROM plan_excursions WHERE ticker = :t AND session_date = :d '
                   'AND rule_version = :v')
    assert bound == {'t': 'TST', 'd': '2026-05-06', 'v': LEVEL_RULE_VERSION}


def test_a_basis_with_no_rule_version_writes_nothing(monkeypatch):
    import json

    row = _v3_row()
    basis = json.loads(row.loc[0, 'level_basis'])
    basis.pop('rule_version')
    row.loc[0, 'level_basis'] = json.dumps(basis)
    _, calls = _resolve(monkeypatch, row, _CALLS_TRADE_BARS)
    assert len(calls) == 1 and calls[0][0].startswith('UPDATE premarket_analysis SET ')


def test_a_history_write_never_replaces_a_resolver_row_and_deletes_only_its_own():
    import gcp.premarket_playbook_resolver as mod

    plans = {'calls': _calls_plan(), 'puts': _puts_plan()}
    ex = ExcursionResult(fill_i=1, fill_price=100.0, fill_ts=_ts(1), stop_i=None,
                         stop_ts=None, excursion_r=1.5, excursion_held5_r=1.2)
    sql, bound = mod.excursion_statement('spy', '2025-10-22', 'feat-strat-001.v3',
                                         ('calls', ex), plans, 'history')
    assert sql.text.endswith("DO UPDATE SET side = EXCLUDED.side, trigger_price = EXCLUDED.trigger_price, "
                             "stop_price = EXCLUDED.stop_price, fill_price = EXCLUDED.fill_price, "
                             "fill_ts = EXCLUDED.fill_ts, stop_ts = EXCLUDED.stop_ts, "
                             "excursion_r = EXCLUDED.excursion_r, "
                             "excursion_held5_r = EXCLUDED.excursion_held5_r, "
                             "source = EXCLUDED.source, resolver_version = EXCLUDED.resolver_version, "
                             "written_at = EXCLUDED.written_at WHERE plan_excursions.source = 'history'")
    assert bound['source'] == 'history' and bound['t'] == 'SPY'
    sql, _ = mod.excursion_statement('spy', '2025-10-22', 'feat-strat-001.v3', None, plans, 'history')
    assert sql.text.endswith("AND rule_version = :v AND source = 'history'")
    assert mod.excursion_statement('spy', '2025-10-22', None, ('calls', ex), plans, 'history') is None


# ── FEAT-PLAYBOOK-001 B8b: a v3 plan resolves as before the bump ────────

@pytest.mark.parametrize('version', ['feat-strat-001.v3', 'feat-strat-001.v4',
                                     'feat-strat-001.v5'])
def test_v3_plan_resolves_as_on_main(version):
    """The literals are plan_inputs on d8_basis() as printed on the unchanged
    code (head 219a4c0c3, where the fixture was v3)."""
    import gcp.premarket_playbook_resolver as mod
    from tests.lib.session_levels_helpers import d8_basis

    basis = {**d8_basis(), 'rule_version': version}
    no_policy = lambda: pytest.fail('no policy read')  # noqa: E731
    calls = mod.plan_inputs('calls', {}, basis, policy_fn=no_policy)
    assert calls == mod.PlanInputs(trigger_price=252.1, stop_price=248.2,
                                   targets=(275.0, 280.0, 285.0), legs=3,
                                   cutoff_minutes=960, target_status='ok')
    puts = mod.plan_inputs('puts', {}, basis, policy_fn=no_policy)
    assert puts == mod.PlanInputs(trigger_price=248.2, stop_price=252.1,
                                  targets=(225.0, 220.0, 215.0), legs=3,
                                  cutoff_minutes=960, target_status='ok')
    assert calls.target_status != mod.PLAN_TARGETS_UNAVAILABLE
    assert puts.target_status != mod.PLAN_TARGETS_UNAVAILABLE


# ── Unknown rule version spec (2026-11-16), Design 3: the resolver row ──
# A stored basis of a version this image does not know, or cannot read, is
# refused: resolve_one writes nothing and reads no bars, so the row stays
# pending and a compatible image resolves it inside the lookback.

import logging  # noqa: E402

from tests.lib.session_levels_helpers import newer_rule_versions  # noqa: E402

# The v3 plan row of test_resolve_one_binds_the_plan_columns_from_a_v3_basis:
# its calls and puts trigger, stop and t1 to t3 columns all populated, so it
# never reaches from_basis and the resolver's own check is its only guard.
V3_PLAN_COLUMNS = {
    'calls_trigger_price': 252.10, 'calls_stop_price': 248.20,
    'calls_t1_price': 253.00, 'calls_t2_price': 275.00, 'calls_t3_price': 280.00,
    'puts_trigger_price': 248.20, 'puts_stop_price': 252.10,
    'puts_t1_price': 247.50, 'puts_t2_price': 247.00, 'puts_t3_price': 225.00,
}

REFUSED_VERSIONS = [*((v, 'rule_version_newer') for v in newer_rule_versions()),
                    ('', 'rule_version_unreadable'),
                    ('feat-strat-001.vX', 'rule_version_unreadable'),
                    (5, 'rule_version_unreadable')]


def _v3_plan_row(rule_version, *, outcome_resolved_at=None) -> dict:
    """The v3 plan row with a d8 basis stamped `rule_version`."""
    import json

    from tests.lib.session_levels_helpers import d8_basis
    return {**V3_PLAN_COLUMNS,
            'level_basis': json.dumps({**d8_basis(), 'rule_version': rule_version}),
            'outcome_resolved_at': outcome_resolved_at}


def _one_read(row: dict):
    """A pd.read_sql stand-in that answers the row SELECT once and fails the
    test on any second read (the bars, the daily frame, the parameters)."""
    reads = []

    def read_sql(sql, engine, params=None):
        reads.append(getattr(sql, 'text', str(sql)))
        if len(reads) > 1:
            pytest.fail(f'a second read: {reads[-1].strip()[:80]}')
        return pd.DataFrame([row])
    return reads, read_sql


def _error_lines(caplog) -> list:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.parametrize('force, outcome_resolved_at',
                         [(False, None), (True, '2026-11-16T21:00:00Z')])
@pytest.mark.parametrize('version, reason', REFUSED_VERSIONS)
def test_resolve_one_refuses_a_version_it_does_not_know(monkeypatch, caplog, version, reason,
                                                        force, outcome_resolved_at):
    import gcp.premarket_playbook_resolver as mod
    from lib.strat_levels import newest_pick_rule_version

    reads, read_sql = _one_read(_v3_plan_row(version, outcome_resolved_at=outcome_resolved_at))
    monkeypatch.setattr(mod.pd, 'read_sql', read_sql)
    monkeypatch.setattr(mod, 'plan_inputs', lambda *a, **k: pytest.fail('plan_inputs called'))
    monkeypatch.setattr(mod, 'derive_level_map_from_daily',
                        lambda *a, **k: pytest.fail('derive_level_map_from_daily called'))
    engine = _RecordingEngine()

    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = mod.resolve_one(_date(2026, 11, 16), 'tst', engine, force=force)

    assert out == (None, reason)
    assert engine.conn.calls == []
    assert len(reads) == 1
    [line] = _error_lines(caplog)
    for part in ('TST', '2026-11-16', repr(version), reason, newest_pick_rule_version()):
        assert part in line, (part, line)


def test_resolve_one_returns_the_derive_paths_refusal(monkeypatch, caplog):
    """A row with no stored triggers and a legacy (absent) basis of its own
    passes the first check; the session's live basis read by the derive path
    is newer, and that refusal is returned the same way, with no write and
    no bar read."""
    import gcp.premarket_playbook_resolver as mod
    from lib.strat_levels import LevelRuleVersionUnknown

    row = {**{k: None for k in V3_PLAN_COLUMNS}, 'level_basis': None,
           'outcome_resolved_at': None}
    reads, read_sql = _one_read(row)
    monkeypatch.setattr(mod.pd, 'read_sql', read_sql)

    def derive(*a, **k):
        raise LevelRuleVersionUnknown('rule_version_newer', newer_rule_versions()[0])

    monkeypatch.setattr(mod, 'derive_level_map_from_daily', derive)
    monkeypatch.setattr(mod, 'plan_inputs', lambda *a, **k: pytest.fail('plan_inputs called'))
    engine = _RecordingEngine()

    with caplog.at_level(logging.ERROR, logger=mod.logger.name):
        out = mod.resolve_one(_date(2026, 11, 16), 'tst', engine)

    assert out == (None, 'rule_version_newer')
    assert engine.conn.calls == []
    assert len(reads) == 1
    [line] = _error_lines(caplog)
    for part in ('TST', '2026-11-16', repr(newer_rule_versions()[0]), 'rule_version_newer'):
        assert part in line, (part, line)


# ── Unknown rule version spec, decision 3: main() exits non-zero (U4) ───

from datetime import time as _time  # noqa: E402

PLAN_COLUMNS = tuple(f'{side}_plan_{f}' for side in ('calls', 'puts') for f in PLAN_FIELDS)
_ROW_SELECT = tuple(V3_PLAN_COLUMNS) + ('level_basis', 'outcome_resolved_at')


def _session_bars(d: _date) -> pd.DataFrame:
    """The four bars of the v3 plan test at 09:30, 09:31, 09:32 and 15:59
    Eastern on `d`: the calls side enters at 252.10 and books T1."""
    from lib.eastern_time import eastern_bounds_utc
    open_utc = eastern_bounds_utc(d, _time(9, 30), _time(16, 0))[0]
    rows = [(0, 251.00, 251.50, 250.80, 251.40), (1, 251.90, 252.50, 251.80, 252.40),
            (2, 260.00, 276.00, 259.00, 270.00), (389, 270.00, 271.00, 269.00, 270.00)]
    return pd.DataFrame([{'time': open_utc + timedelta(minutes=m), 'open': o, 'high': h,
                          'low': lo, 'close': c} for m, o, h, lo, c in rows])


def _table_row(d: _date, ticker: str, rule_version, *, outcome_resolved_at=None, **cols) -> dict:
    """A premarket_analysis row: the v3 plan row with a d8 basis stamped
    `rule_version`, every plan column NULL unless `cols` says otherwise."""
    row = {'analysis_date': d, 'ticker': ticker,
           **_v3_plan_row(rule_version, outcome_resolved_at=outcome_resolved_at),
           **{c: None for c in PLAN_COLUMNS}}
    row.update(cols)
    return row


class _ResolverTable:
    """premarket_analysis and the day's bars in memory, behind the four
    statements main() issues. An UPDATE premarket_analysis is applied to the
    row its d and t name; the day's plan_excursions write (target hit rates
    spec, Design 4) is kept apart in excursion_writes; any other statement
    fails the test."""

    def __init__(self, rows: list, bars_for):
        self.rows = rows
        self.bars_for = bars_for
        self.statements = []
        self.writes = []
        self.excursion_writes = []
        self.pending_answers = []
        table = self

        class _Conn:
            def execute(self, sql, params=None):
                sql_text = getattr(sql, 'text', str(sql))
                bound = dict(params or {})
                if 'plan_excursions' in sql_text.split('WHERE')[0]:
                    table.excursion_writes.append((sql_text, bound))
                    return
                table.statements.append((sql_text, bound))
                if not sql_text.startswith('UPDATE premarket_analysis SET '):
                    pytest.fail(f'unexpected write: {sql_text[:80]}')
                [row] = [r for r in table.rows
                         if str(r['analysis_date']) == bound['d'] and r['ticker'] == bound['t']]
                row.update({k: v for k, v in bound.items() if k not in ('d', 't')})
                table.writes.append((sql_text, bound))

        class _Engine:
            def begin(self):
                from contextlib import contextmanager

                @contextmanager
                def _cm():
                    yield _Conn()
                return _cm()

        self.engine = _Engine()

    def read_sql(self, sql, engine, params=None):
        sql_text = getattr(sql, 'text', str(sql))
        p = dict(params or {})
        self.statements.append((sql_text, p))
        if 'SELECT DISTINCT analysis_date FROM premarket_analysis' in sql_text:
            today, floor = _date.fromisoformat(p['today']), _date.fromisoformat(p['floor'])
            dates = sorted({r['analysis_date'] for r in self.rows
                            if r['outcome_resolved_at'] is None
                            and floor <= r['analysis_date'] <= today
                            and r['analysis_date'].weekday() < 5})
            self.pending_answers.append(dates)
            return pd.DataFrame({'analysis_date': pd.Series(dates, dtype=object)})
        if 'SELECT DISTINCT ticker FROM premarket_analysis' in sql_text:
            return pd.DataFrame({'ticker': pd.Series(
                [r['ticker'] for r in self.rows if str(r['analysis_date']) == p['d']],
                dtype=object)})
        if 'level_basis, outcome_resolved_at' in sql_text and 'LIMIT 1' in sql_text:
            hits = [r for r in self.rows
                    if str(r['analysis_date']) == p['d'] and r['ticker'] == p['t']]
            return pd.DataFrame([{c: r[c] for c in _ROW_SELECT} for r in hits[:1]])
        if 'FROM market_data_intraday' in sql_text:
            return self.bars_for(_date.fromisoformat(p['d']))
        pytest.fail(f'unexpected read: {sql_text.strip()[:80]}')


def _run_main(monkeypatch, table, *, pick=None, **env) -> int:
    """main() at 2026-11-17 20:00 Eastern against `table`, with only the
    PLAYBOOK_RESOLVE_* variables in `env` set; `pick` patches
    lib.strat_levels.PICK_RULE_VERSIONS (a straggler image)."""
    import os

    import gcp.database
    import gcp.premarket_playbook_resolver as mod
    import lib.strat_levels

    for key in [k for k in os.environ if k.startswith('PLAYBOOK_RESOLVE_')]:
        monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 17, 20, 0, tzinfo=tz)

    monkeypatch.setattr(gcp.database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(gcp.database, 'get_engine', lambda *a, **k: table.engine)
    monkeypatch.setattr(mod.pd, 'read_sql', table.read_sql)
    monkeypatch.setattr(mod, 'datetime', _Now)
    if pick is not None:
        monkeypatch.setattr(lib.strat_levels, 'PICK_RULE_VERSIONS', pick)
    return mod.main([])


@pytest.mark.parametrize('version, reason', [(newer_rule_versions()[0], 'rule_version_newer'),
                                             ('', 'rule_version_unreadable')])
def test_main_exits_non_zero_on_a_refused_row(monkeypatch, caplog, version, reason):
    """Decision 3: a refused row on today's date, which classify_date_outcome
    would call benign_pending, still turns the run red."""
    import gcp.premarket_playbook_resolver as mod
    from lib.strat_levels import newest_pick_rule_version

    table = _ResolverTable([_table_row(_date(2026, 11, 17), 'TST', version)], _session_bars)
    with caplog.at_level(logging.INFO, logger=mod.logger.name):
        assert _run_main(monkeypatch, table) == 1
    assert table.writes == []
    assert any(all(part in line for part in ('TST', '2026-11-17', repr(version), reason,
                                             newest_pick_rule_version()))
               for line in _error_lines(caplog)), _error_lines(caplog)


def test_main_exits_non_zero_on_a_refused_row_on_a_past_date(monkeypatch, caplog):
    """A refused row alone on a past date does not read as nothing to do:
    the date's done line counts it and the run exits 1."""
    import gcp.premarket_playbook_resolver as mod

    table = _ResolverTable([_table_row(_date(2026, 11, 16), 'TST', newer_rule_versions()[0])],
                           _session_bars)
    with caplog.at_level(logging.INFO, logger=mod.logger.name):
        assert _run_main(monkeypatch, table) == 1
    assert table.writes == []
    done = [r.getMessage() for r in caplog.records
            if r.levelno == logging.INFO and r.getMessage().startswith('done 2026-11-16:')]
    assert len(done) == 1 and '1 refused' in done[0], done


# ── Unknown rule version spec, Design 4: recovery goes through the scheduled
# run (U7b). Today is 2026-11-17, the default lookback 14 days (floor
# 2026-11-03), PLAYBOOK_RESOLVE_DATE unset unless a case says so. A straggler
# image knows v3 only; a compatible one knows what this tree knows.

class TestScheduledRecovery:
    STRAGGLER = ('feat-strat-001.v3',)
    V3 = 'feat-strat-001.v3'

    @staticmethod
    def _kept(row: dict) -> dict:
        return {c: row[c] for c in ('outcome_resolved_at', *PLAN_COLUMNS)}

    @staticmethod
    def _v4():
        from lib.strat_levels import LEVEL_RULE_VERSION
        return LEVEL_RULE_VERSION

    def _straggler_run(self, monkeypatch, table, **env) -> int:
        with monkeypatch.context() as mp:
            return _run_main(mp, table, pick=self.STRAGGLER, **env)

    def test_a_straggler_resolves_the_row_it_knows_and_leaves_the_other(self, monkeypatch):
        aaa = _table_row(_date(2026, 11, 16), 'AAA', self.V3)
        bbb = _table_row(_date(2026, 11, 16), 'BBB', self._v4())
        before = self._kept(bbb)
        table = _ResolverTable([aaa, bbb], _session_bars)

        rc = self._straggler_run(monkeypatch, table)
        assert self._kept(bbb) == before
        assert [b['t'] for _, b in table.writes] == ['AAA']
        assert aaa['outcome_resolved_at'] is not None
        assert aaa['calls_plan_r_status'] == 'ok'
        assert rc == 1

    def test_a_compatible_image_resolves_it_unforced(self, monkeypatch):
        aaa = _table_row(_date(2026, 11, 16), 'AAA', self.V3)
        bbb = _table_row(_date(2026, 11, 16), 'BBB', self._v4())
        table = _ResolverTable([aaa, bbb], _session_bars)
        assert self._straggler_run(monkeypatch, table) == 1

        assert _run_main(monkeypatch, table) == 0
        assert table.pending_answers[-1] == [_date(2026, 11, 16)]
        assert bbb['outcome_resolved_at'] is not None
        assert bbb['calls_plan_r_status'] == 'ok'
        assert [b['t'] for _, b in table.writes] == ['AAA', 'BBB']

    def test_the_lookback_boundary(self, monkeypatch):
        inside = _table_row(_date(2026, 11, 3), 'TST', self._v4())
        outside = _table_row(_date(2026, 11, 2), 'TST', self._v4())
        before = self._kept(outside)
        table = _ResolverTable([inside, outside], _session_bars)

        assert _run_main(monkeypatch, table) == 0
        assert table.pending_answers == [[_date(2026, 11, 3)]]
        assert [b['d'] for _, b in table.writes] == ['2026-11-03']
        assert inside['calls_plan_r_status'] == 'ok'
        assert self._kept(outside) == before

    def test_after_age_out(self, monkeypatch):
        row = _table_row(_date(2026, 11, 2), 'TST', self._v4())
        table = _ResolverTable([row], _session_bars)

        assert self._straggler_run(monkeypatch, table) == 0
        assert table.pending_answers == [[]]
        assert not any('2026-11-02' in sql or '2026-11-02' in map(str, bound.values())
                       for sql, bound in table.statements)
        assert table.writes == []

        assert _run_main(monkeypatch, table, PLAYBOOK_RESOLVE_DATE='2026-11-02') == 0
        assert [b['d'] for _, b in table.writes] == ['2026-11-02']
        assert row['calls_plan_r_status'] == 'ok'

    def test_a_row_an_older_reader_stamped(self, monkeypatch):
        def _stamped():
            return _table_row(_date(2026, 11, 16), 'TST', self._v4(),
                              outcome_resolved_at=datetime(2026, 11, 16, 21, 15),
                              calls_plan_r_status='targets_unavailable',
                              puts_plan_r_status='targets_unavailable', calls_plan_r=None)
        row = _stamped()
        table = _ResolverTable([row], _session_bars)

        assert _run_main(monkeypatch, table) == 0
        assert _run_main(monkeypatch, table, PLAYBOOK_RESOLVE_FORCE='true') == 0
        assert table.writes == []
        assert _run_main(monkeypatch, table, PLAYBOOK_RESOLVE_DATE='2026-11-16',
                         PLAYBOOK_RESOLVE_FORCE='true') == 0
        assert len(table.writes) == 1
        assert row['calls_plan_r_status'] == 'ok'

        fresh = _stamped()
        before = self._kept(fresh)
        table = _ResolverTable([fresh], _session_bars)
        rc = self._straggler_run(monkeypatch, table, PLAYBOOK_RESOLVE_DATE='2026-11-16',
                                 PLAYBOOK_RESOLVE_FORCE='true')
        assert table.writes == []
        assert self._kept(fresh) == before
        assert rc == 1

    def test_an_unreadable_version_is_refused_by_every_image(self, monkeypatch, caplog):
        import gcp.premarket_playbook_resolver as mod

        rows = [_table_row(_date(2026, 11, 16), t, v)
                for t, v in (('UA', ''), ('UB', 'feat-strat-001.vX'), ('UC', 5))]
        before = [self._kept(r) for r in rows]
        table = _ResolverTable(rows, _session_bars)

        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            rc = _run_main(monkeypatch, table)
        assert [b['t'] for _, b in table.writes] == []
        assert [self._kept(r) for r in rows] == before
        assert rc == 1
        for t in ('UA', 'UB', 'UC'):
            lines = [line for line in _error_lines(caplog) if line.startswith(f'{t} ')]
            assert len(lines) == 1 and 'rule_version_unreadable' in lines[0], (t, lines)
