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
    assert mod.RESOLVER_VERSION == '2026-11-12.v3'
    assert bound['outcome_resolver_version'] == '2026-11-12.v3'
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
        assert calls.legs == 3 and calls.cutoff_minutes == CUTOFF_10_ET
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
        assert calls.legs == 3 and calls.cutoff_minutes == CUTOFF_10_ET
        assert calls.plan_available

    def test_a_row_without_level_basis_has_no_plan(self):
        import gcp.premarket_playbook_resolver as mod

        row = {'calls_trigger_price': 100.0, 'calls_stop_price': 99.0}
        calls = mod.plan_inputs('calls', row, None, policy_fn=lambda: pytest.fail('no policy read'))
        assert calls.target_status == 'targets_unavailable' and not calls.plan_available


def _plan_set_and_bound(engine):
    [(sql, bound)] = engine.conn.calls
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
