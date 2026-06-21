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
    find_atm_option,
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


# ──────────────────────────────────────────────────────────────────────
# Column-semantics regression — delta_pnl / theta_cost MUST be NaN in
# realtime rows so downstream aggregations don't silently mix
# Greeks-decomposed numbers with mark-to-mark gross P&L. See
# estimate_options_pnl docstring "Column semantics" table.
# ──────────────────────────────────────────────────────────────────────


class TestRealtimeRowSchema:

    def test_realtime_row_has_nan_delta_pnl(self):
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        rt = _realtime_marks(d, [0, 5, 10, 15], [2.50, 2.50, 2.80, 3.00])
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        assert result['data_source'] == DATA_SOURCE_REALTIME
        assert np.isnan(result['delta_pnl']), \
            "realtime delta_pnl must be NaN — mark-to-mark P&L can't " \
            "be decomposed into Greeks contributions without re-pricing"

    def test_realtime_row_has_nan_theta_cost(self):
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        rt = _realtime_marks(d, [0, 5, 10, 15], [2.50, 2.50, 2.80, 3.00])
        result = estimate_options_pnl(trade, atm, realtime_marks=rt)
        assert np.isnan(result['theta_cost']), \
            "realtime theta_cost must be NaN — theta drag is folded " \
            "into the observed mark already"

    def test_fallback_row_has_numeric_delta_pnl_and_theta_cost(self):
        d = date(2020, 7, 31)
        trade = _trade(entry_min=9*60+35, hold_min=30.0, trade_date=d,
                       return_pct=0.005)
        atm = _atm_chain_row(strike=500.0, mark=2.50,
                             expiration=date(2020, 8, 1))
        result = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert result['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK
        # Decomposed: eff_delta * |chg| = 0.5 * (500 * 0.005) = 1.25
        assert result['delta_pnl'] == pytest.approx(1.25, abs=0.01)
        # |theta| * hold/1440 = 0.20 * 30/1440 = 0.00417
        assert result['theta_cost'] == pytest.approx(0.00417, abs=0.001)

    def test_pandas_mean_skips_realtime_rows_safely(self):
        """The whole point of the NaN: pd.DataFrame(['delta_pnl']).mean()
        across mixed rows must reflect ONLY the fallback semantics, not
        an incoherent mix of gross-P&L (realtime) and delta-attributed
        (fallback)."""
        d_realtime = date(2026, 5, 22)
        d_fallback = date(2020, 7, 31)
        trade_rt = _trade(entry_min=9*60+35, hold_min=10.0,
                          trade_date=d_realtime)
        trade_fb = _trade(entry_min=9*60+35, hold_min=30.0,
                          trade_date=d_fallback, return_pct=0.005)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d_realtime)
        rt = _realtime_marks(d_realtime, [0, 5, 10, 15],
                             [2.50, 2.50, 2.80, 3.00])
        r1 = estimate_options_pnl(trade_rt, atm, realtime_marks=rt)
        r2 = estimate_options_pnl(trade_fb, atm, realtime_marks=None)
        df = pd.DataFrame([r1, r2])
        # NaN-skipped mean equals the fallback row's value alone — not
        # corrupted by averaging in a 0.30 gross-P&L from the realtime row.
        assert df['delta_pnl'].mean() == pytest.approx(1.25, abs=0.01)
        assert df['theta_cost'].mean() == pytest.approx(0.00417, abs=0.001)


# ──────────────────────────────────────────────────────────────────────
# Codex 2026-06-13: load_options_chain must exclude REALTIME rows so
# find_atm_option can never pick an intraday snapshot as the "EOD chain
# row" — both have data_source='alphavantage' but the EOD path assumes
# end-of-day Greeks. See PR #614 review.
# ──────────────────────────────────────────────────────────────────────


class TestLoadOptionsChainExcludesRealtime:
    """The SQL emitted by load_options_chain must filter REALTIME rows out
    of the EOD chain result set. Failing to do so corrupts the
    Greeks-approximation fallback path of estimate_options_pnl because
    find_atm_option could pick a mid-day REALTIME snapshot as the "ATM
    chain row" — its delta/theta are intraday Greeks, not EOD."""

    def test_sql_excludes_realtime_market_session(self, monkeypatch):
        captured = {}

        def fake_query(sql, params):
            captured['sql'] = sql
            return pd.DataFrame()  # query result irrelevant for this test

        monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'fake')
        monkeypatch.setattr(
            'gcp.database.query_to_dataframe', fake_query)

        from scripts.analysis.options_pnl_translation import load_options_chain
        load_options_chain('SPY', date(2026, 6, 12))

        sql = captured.get('sql', '')
        # The fix: chain query must reject REALTIME rows (NULL allowed for
        # legacy yahooquery EOD rows).
        assert "market_session != 'REALTIME'" in sql, \
            "EOD chain loader must filter REALTIME rows so the ATM picker " \
            "can't accidentally select an intraday snapshot " \
            "(Codex 2026-06-13)"
        assert 'market_session IS NULL' in sql, \
            "Legacy EOD rows (no market_session enum at write time) must " \
            "still be returned by the chain query"


# ──────────────────────────────────────────────────────────────────────
# Happy-path companions — exercise the REAL empirical Greeks-approximation
# math and the REAL ATM picker, asserting financial invariants (sign
# correctness, delta bounds, ATM selection) rather than only round-tripping
# hand-typed values through a DI'd loader. The existing magnitude tests
# (1.25, 0.00417) verify the formula's exact output; these verify the
# direction/sign of P&L is correct across CALL/PUT × favorable/adverse moves,
# which a magnitude-only test can pass while having the sign backwards.
# ──────────────────────────────────────────────────────────────────────


def _put_chain_row(strike: float = 500.0, mark: float = 2.50,
                   delta: float = -0.50, theta: float = -0.20,
                   expiration: date = date(2020, 8, 1)) -> pd.Series:
    """Synthetic EOD AV PUT chain row — put delta is negative."""
    return pd.Series({
        'strike': strike, 'mark': mark,
        'bid': mark - 0.05, 'ask': mark + 0.05,
        'delta': delta, 'gamma': 0.02, 'theta': theta,
        'vega': 0.10, 'rho': -0.05, 'expiration': expiration,
        'type': 'put', 'implied_volatility': 0.30,
    })


class TestEmpiricalPnlSignCorrectness:
    """The empirical Greeks path must get the SIGN of delta_pnl right:
    a CALL profits when the underlying rises and loses when it falls; a PUT
    is the mirror. Sign bugs are the classic options-P&L failure mode a
    magnitude-only assertion misses."""

    def test_call_with_up_move_is_a_win(self):
        d = date(2020, 7, 31)
        trade = _trade(direction='CALL', return_pct=0.02, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, delta=0.50,
                             expiration=date(2020, 8, 1))
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK
        assert r['delta_pnl'] > 0          # favorable move → positive delta P&L
        assert r['net_pnl_dollar'] > 0     # net of theta+spread still a win
        assert r['option_win'] == 1
        assert r['underlying_win'] == 1

    def test_call_with_down_move_is_a_loss(self):
        d = date(2020, 7, 31)
        trade = _trade(direction='CALL', return_pct=-0.02, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, delta=0.50,
                             expiration=date(2020, 8, 1))
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['delta_pnl'] < 0          # adverse move → negative delta P&L
        assert r['net_pnl_dollar'] < 0
        assert r['option_win'] == 0
        assert r['underlying_win'] == 0

    def test_put_with_down_move_is_a_win(self):
        """A PUT profits when the underlying FALLS. The chain row carries a
        negative delta; the code takes |delta| and re-signs by direction —
        the result must be a positive delta P&L for a down move."""
        d = date(2020, 7, 31)
        trade = _trade(direction='PUT', return_pct=-0.02, trade_date=d)
        atm = _put_chain_row(strike=500.0, mark=2.50, delta=-0.50)
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['delta_pnl'] > 0
        assert r['net_pnl_dollar'] > 0
        assert r['option_win'] == 1
        assert r['underlying_win'] == 0    # underlying fell, so underlying "loss"

    def test_put_with_up_move_is_a_loss(self):
        d = date(2020, 7, 31)
        trade = _trade(direction='PUT', return_pct=0.02, trade_date=d)
        atm = _put_chain_row(strike=500.0, mark=2.50, delta=-0.50)
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['delta_pnl'] < 0
        assert r['net_pnl_dollar'] < 0
        assert r['option_win'] == 0

    def test_net_pnl_pct_is_return_on_premium(self):
        """net_pnl_pct must equal net_pnl_dollar / mark (return on premium
        paid) — an internal-consistency invariant, not a hand-typed number."""
        d = date(2020, 7, 31)
        trade = _trade(direction='CALL', return_pct=0.02, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, delta=0.50,
                             expiration=date(2020, 8, 1))
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['net_pnl_pct'] == pytest.approx(
            r['net_pnl_dollar'] / r['mark'], rel=1e-9)

    def test_theta_and_spread_are_costs_not_credits(self):
        """A flat underlying move (return_pct ~ 0) must still LOSE money to
        theta decay + half-spread — both are costs, so net < 0."""
        d = date(2020, 7, 31)
        trade = _trade(direction='CALL', return_pct=0.0, hold_min=120.0,
                       trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, delta=0.50,
                             theta=-0.40, expiration=date(2020, 8, 1))
        r = estimate_options_pnl(trade, atm, realtime_marks=None)
        assert r['theta_cost'] > 0          # stored as a positive cost
        assert r['spread_cost'] > 0
        assert r['net_pnl_dollar'] < 0      # no move, only costs → loss


class TestFindAtmOptionRealPicker:
    """Exercise the REAL ATM selector against a realistic multi-strike,
    multi-expiry chain — verifies it picks the nearest strike, the right
    option type, and prefers the 0DTE expiry."""

    def _chain(self):
        return pd.DataFrame([
            # 0DTE expiry (trade date)
            {'type': 'call', 'strike': 495, 'expiration': date(2026, 5, 22),
             'mark': 6.1, 'delta': 0.66, 'bid': 6.0, 'ask': 6.2, 'theta': -0.3},
            {'type': 'call', 'strike': 500, 'expiration': date(2026, 5, 22),
             'mark': 2.5, 'delta': 0.50, 'bid': 2.45, 'ask': 2.55, 'theta': -0.2},
            {'type': 'call', 'strike': 510, 'expiration': date(2026, 5, 22),
             'mark': 0.8, 'delta': 0.22, 'bid': 0.75, 'ask': 0.85, 'theta': -0.1},
            {'type': 'put', 'strike': 500, 'expiration': date(2026, 5, 22),
             'mark': 2.4, 'delta': -0.50, 'bid': 2.35, 'ask': 2.45, 'theta': -0.2},
            # later expiry — must NOT be chosen when a 0DTE strike exists
            {'type': 'call', 'strike': 501, 'expiration': date(2026, 5, 29),
             'mark': 5.0, 'delta': 0.52, 'bid': 4.9, 'ask': 5.1, 'theta': -0.05},
        ])

    def test_picks_nearest_strike_call_zero_dte(self):
        atm = find_atm_option(self._chain(), entry_price=501.5,
                              trade_date=date(2026, 5, 22), direction='CALL')
        assert not atm.empty
        assert atm['type'] == 'call'
        assert atm['strike'] == 500          # 500 is nearest to 501.5
        assert pd.Timestamp(atm['expiration']).date() == date(2026, 5, 22)  # 0DTE

    def test_picks_put_for_put_direction(self):
        atm = find_atm_option(self._chain(), entry_price=500.0,
                              trade_date=date(2026, 5, 22), direction='PUT')
        assert not atm.empty
        assert atm['type'] == 'put'
        assert atm['delta'] < 0              # a real put delta

    def test_falls_back_to_nearest_future_expiry_when_no_zero_dte(self):
        """No 0DTE for the trade date → the picker must use the nearest
        FUTURE expiry, never an already-expired contract."""
        chain = pd.DataFrame([
            {'type': 'call', 'strike': 500, 'expiration': date(2026, 5, 29),
             'mark': 5.0, 'delta': 0.52, 'bid': 4.9, 'ask': 5.1, 'theta': -0.05},
            {'type': 'call', 'strike': 500, 'expiration': date(2026, 6, 5),
             'mark': 7.0, 'delta': 0.54, 'bid': 6.9, 'ask': 7.1, 'theta': -0.04},
        ])
        atm = find_atm_option(chain, entry_price=500.0,
                              trade_date=date(2026, 5, 22), direction='CALL')
        assert not atm.empty
        assert pd.Timestamp(atm['expiration']).date() == date(2026, 5, 29)  # nearest future

    def test_empty_chain_returns_empty_series(self):
        atm = find_atm_option(pd.DataFrame(), entry_price=500.0,
                              trade_date=date(2026, 5, 22), direction='CALL')
        assert atm.empty


class TestRealtimePnlSignCorrectness:
    """Realtime mark-to-mark P&L sign must track the observed mark change,
    and net_pnl_pct must be measured on the entry mark."""

    def _marks(self, vals):
        d = date(2026, 5, 22)
        return _realtime_marks(d, [0, 5, 10, 15], vals)

    def test_realtime_gain_when_mark_rises(self):
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        r = estimate_options_pnl(trade, atm,
                                 realtime_marks=self._marks([2.50, 2.50, 2.80, 3.00]))
        assert r['data_source'] == DATA_SOURCE_REALTIME
        assert r['net_pnl_dollar'] > 0
        assert r['option_win'] == 1
        # net_pnl_pct measured on entry mark (≈2.50), not the EOD chain mark.
        assert r['net_pnl_pct'] == pytest.approx(
            r['net_pnl_dollar'] / r['mark'], rel=1e-9)

    def test_realtime_loss_when_mark_falls(self):
        d = date(2026, 5, 22)
        trade = _trade(entry_min=9*60+35, hold_min=10.0, trade_date=d)
        atm = _atm_chain_row(strike=500.0, mark=2.50, expiration=d)
        r = estimate_options_pnl(trade, atm,
                                 realtime_marks=self._marks([2.50, 2.50, 2.20, 2.00]))
        assert r['data_source'] == DATA_SOURCE_REALTIME
        assert r['net_pnl_dollar'] < 0
        assert r['option_win'] == 0
