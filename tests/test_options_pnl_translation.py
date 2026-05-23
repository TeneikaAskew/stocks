"""Hermetic tests for scripts/analysis/options_pnl_translation.py.

Focus: the Track 2 phase 2a additions — realtime mark-to-mark P&L as the
primary path, empirical Greeks-approximation as the explicit fallback,
``data_source`` column propagation, and the new ``load_realtime_marks``
loader. The original EOD-options-chain loader and combo runner are
covered indirectly by the larger backtest suite; this file is
purposefully narrow to the Track 2 additions.

All tests inject ``query_fn`` rather than hitting Cloud SQL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.options_pnl_translation import (
    estimate_options_pnl,
    find_realtime_mark_at,
    load_realtime_marks,
)
from lib.options_intraday import (
    DATA_SOURCE_EMPIRICAL_FALLBACK,
    DATA_SOURCE_REALTIME,
)


# ──────────────────────────────────────────────────────────────────────
# Synthetic factories
# ──────────────────────────────────────────────────────────────────────

def _trade(entry_min: int = 9*60 + 35, hold_min: float = 30.0,
           direction: str = 'CALL', return_pct: float = 0.005,
           entry_price: float = 500.0,
           trade_date: date = date(2026, 5, 22)) -> pd.Series:
    """Build a synthetic trade row matching the analyser's expected schema."""
    entry_time = datetime.combine(trade_date, datetime.min.time()) \
                 + timedelta(minutes=entry_min)
    return pd.Series({
        'trade_date':   trade_date,
        'direction':    direction,
        'entry_price':  entry_price,
        'entry_time':   entry_time,
        'return_pct':   return_pct,
        'hold_min':     hold_min,
        'hhmm':         entry_time.hour * 100 + entry_time.minute,
    })


def _atm_chain_row(strike: float = 500.0, mark: float = 2.50,
                   delta: float = 0.50, theta: float = -0.20,
                   expiration: date = date(2026, 5, 22)) -> pd.Series:
    """Build a synthetic EOD AV chain row (find_atm_option output shape)."""
    return pd.Series({
        'strike':     strike,
        'mark':       mark,
        'bid':        mark - 0.05,
        'ask':        mark + 0.05,
        'delta':      delta,
        'gamma':      0.02,
        'theta':      theta,
        'vega':       0.10,
        'rho':        0.05,
        'expiration': expiration,
        'type':       'call',
        'implied_volatility': 0.30,
    })


def _realtime_marks(trade_date: date,
                    minutes_after_open: list[int],
                    marks: list[float],
                    bids: list[float] | None = None,
                    asks: list[float] | None = None) -> pd.DataFrame:
    """Build a synthetic REALTIME marks DataFrame.

    Mirrors the column shape returned by ``load_realtime_marks``.
    """
    n = len(minutes_after_open)
    assert len(marks) == n
    bids = bids if bids is not None else [m - 0.05 for m in marks]
    asks = asks if asks is not None else [m + 0.05 for m in marks]
    return pd.DataFrame({
        'snapshot_ts': [
            datetime.combine(trade_date, datetime.min.time())
            + timedelta(minutes=(9*60 + 30) + m)
            for m in minutes_after_open
        ],
        'mark':  marks,
        'bid':   bids,
        'ask':   asks,
        'delta': [0.50] * n,
        'theta': [-0.20] * n,
    })


# ──────────────────────────────────────────────────────────────────────
# load_realtime_marks — DI'd loader
# ──────────────────────────────────────────────────────────────────────

class TestLoadRealtimeMarks:

    def test_returns_dataframe_when_snapshots_exist(self):
        captured = {}

        def fake_query(sql, params):
            captured['sql'] = sql
            captured['params'] = params
            return _realtime_marks(date(2026, 5, 22), [0, 5, 10],
                                   [2.50, 2.45, 2.40])

        out = load_realtime_marks(
            ticker='spy', trade_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='call', query_fn=fake_query,
        )
        assert len(out) == 3
        assert captured['params']['ticker'] == 'SPY'
        assert captured['params']['ot'] == 'calls'
        assert captured['params']['strike'] == 500.0
        assert "market_session = 'REALTIME'" in captured['sql']

    def test_puts_option_type_maps_to_schema(self):
        captured = {}

        def fake_query(sql, params):
            captured['params'] = params
            return _realtime_marks(date(2026, 5, 22), [0], [2.0])

        load_realtime_marks(
            ticker='SPY', trade_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='put', query_fn=fake_query,
        )
        assert captured['params']['ot'] == 'puts'

    def test_returns_empty_on_empty_response(self):
        out = load_realtime_marks(
            ticker='SPY', trade_date=date(2020, 1, 2),
            expiration=date(2020, 1, 3), strike=300.0,
            option_type='call',
            query_fn=lambda sql, params: pd.DataFrame(),
        )
        assert out.empty

    def test_drops_rows_with_nan_mark(self):
        df = _realtime_marks(date(2026, 5, 22), [0, 5, 10],
                             [2.50, float('nan'), 2.40])
        out = load_realtime_marks(
            ticker='SPY', trade_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='call',
            query_fn=lambda sql, params: df,
        )
        assert len(out) == 2
        assert out['mark'].tolist() == [2.50, 2.40]


# ──────────────────────────────────────────────────────────────────────
# find_realtime_mark_at — nearest-snapshot matcher
# ──────────────────────────────────────────────────────────────────────

class TestFindRealtimeMarkAt:

    def test_returns_nearest_snapshot_within_tolerance(self):
        df = _realtime_marks(date(2026, 5, 22), [0, 5, 10],
                             [2.50, 2.45, 2.40])
        # Looking for 9:33 — snapshots at 9:30 / 9:35 / 9:40. Nearest is
        # 9:35 (2 min off) vs 9:30 (3 min off).
        target = datetime.combine(date(2026, 5, 22), datetime.min.time()) \
                 + timedelta(minutes=9*60+33)
        row = find_realtime_mark_at(df, target)
        assert not row.empty
        assert row['mark'] == 2.45

    def test_returns_empty_outside_tolerance(self):
        df = _realtime_marks(date(2026, 5, 22), [0, 5, 10],
                             [2.50, 2.45, 2.40])
        # 30 min after last snapshot → outside 5 min tolerance
        target = datetime.combine(date(2026, 5, 22), datetime.min.time()) \
                 + timedelta(minutes=9*60+40 + 25)
        row = find_realtime_mark_at(df, target)
        assert row.empty

    def test_handles_empty_input(self):
        row = find_realtime_mark_at(pd.DataFrame(),
                                    datetime(2026, 5, 22, 14, 30))
        assert row.empty


# ──────────────────────────────────────────────────────────────────────
# estimate_options_pnl — realtime vs fallback dispatch
# ──────────────────────────────────────────────────────────────────────

class TestEstimateOptionsPnl:

    def test_realtime_path_tags_data_source(self):
        """When realtime_marks brackets the entry+exit, P&L = observed
        mark_exit - mark_entry - spread_cost."""
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        # Entry at 9:35 → snap to 9:35 mark=2.50; exit at 9:45 → snap to
        # 9:45 mark=3.00. Bid/ask = 2.45/2.55 at entry → spread_cost=0.05.
        # Realized P&L = 3.00 - 2.50 - 0.05 = 0.45.
        rt = _realtime_marks(
            d, [0, 5, 10, 15], [2.50, 2.50, 2.80, 3.00],
            bids=[2.45, 2.45, 2.75, 2.95],
            asks=[2.55, 2.55, 2.85, 3.05],
        )
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        assert result is not None
        assert result['data_source'] == DATA_SOURCE_REALTIME
        assert result['net_pnl_dollar'] == pytest.approx(0.45, abs=0.01)
        assert result['mark'] == pytest.approx(2.50, abs=0.01)
        assert result['option_win'] == 1

    def test_realtime_loss_flagged(self):
        """Mark dropped from 2.50 → 2.10, spread 0.05 → net -0.45 loss."""
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        rt = _realtime_marks(
            d, [0, 5, 10, 15], [2.50, 2.50, 2.30, 2.10],
        )
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        assert result['data_source'] == DATA_SOURCE_REALTIME
        assert result['net_pnl_dollar'] < 0
        assert result['option_win'] == 0

    def test_empirical_fallback_when_no_realtime(self):
        """No realtime data → empirical Greeks approximation, data_source
        stamped fallback."""
        d = date(2020, 7, 31)  # Pre-Track-0 date
        trade = _trade(entry_min=9*60+35, hold_min=30.0, trade_date=d,
                       return_pct=0.005)
        atm = _atm_chain_row(strike=500.0, mark=2.50,
                             expiration=date(2020, 8, 1))
        result = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert result is not None
        assert result['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK

    def test_empirical_fallback_when_realtime_outside_tolerance(self):
        """Realtime exists but the trade's entry/exit minutes fall
        outside any snapshot's ±5 min window → fall back."""
        d = date(2026, 5, 22)
        # Trade entry at 14:30 with 60-min hold; realtime only covers
        # 9:30-9:45 — both entry and exit are far outside any snapshot.
        trade = _trade(entry_min=14*60+30, hold_min=60.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        rt = _realtime_marks(d, [0, 5, 10, 15], [2.50, 2.50, 2.50, 2.50])
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        assert result is not None
        assert result['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK

    def test_realtime_path_uses_observed_spread(self):
        """When entry snapshot has bid/ask, realtime spread cost = (ask-bid)/2
        — NOT the EOD-row's spread."""
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        # EOD chain bid/ask = 2.45/2.55 (spread=0.05);
        # Realtime entry snapshot has WIDER bid/ask = 2.30/2.70 (spread=0.20).
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        rt = _realtime_marks(
            d, [0, 5, 10, 15], [2.50, 2.50, 2.50, 2.50],
            bids=[2.30, 2.30, 2.30, 2.30],
            asks=[2.70, 2.70, 2.70, 2.70],
        )
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        # spread_cost = (2.70 - 2.30) / 2 = 0.20; mark_exit - mark_entry = 0
        # → net = 0 - 0.20 = -0.20
        assert result['spread_cost'] == pytest.approx(0.20, abs=0.01)
        assert result['net_pnl_dollar'] == pytest.approx(-0.20, abs=0.01)
        assert result['data_source'] == DATA_SOURCE_REALTIME

    def test_returns_none_when_chain_unusable(self):
        """No mark/delta/theta → can't price, return None regardless of
        realtime availability."""
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = pd.Series({
            'strike': 500.0, 'mark': np.nan, 'bid': 2.45, 'ask': 2.55,
            'delta': np.nan, 'theta': np.nan, 'expiration': d, 'type': 'call',
        })
        result = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert result is None
