"""Tests for gcp/fetchers/backfill_daily_indicators.py.

Validates:
  - --mode=daily auto-discovers tickers with NULL atr_14 in lookback
  - --mode=full enumerates every ticker in the table
  - The per-ticker compute produces indicator rows
  - Empty-input edge cases return clean (no exceptions)
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from gcp.fetchers import backfill_daily_indicators as mod


def _synth_bars(n: int = 60) -> pd.DataFrame:
    """Generate n realistic-looking daily OHLCV bars."""
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = close + rng.normal(0, 0.3, n)
    high = np.maximum(open_, close) + rng.uniform(0.2, 1.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.5, n)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        'date': dates, 'Open': open_, 'High': high, 'Low': low,
        'Close': close, 'Volume': rng.integers(1_000_000, 5_000_000, n),
    })


class TestTickerResolution:
    def test_mode_daily_auto_discovers_tickers_with_gaps(self):
        gap_tickers = pd.DataFrame({'ticker': ['AAA', 'BBB']})
        with patch.object(mod, 'query_to_dataframe', return_value=gap_tickers) as qm:
            out = mod._tickers_with_gaps(7)
        assert out == ['AAA', 'BBB']
        # The query must use num_nulls() across every derived column,
        # not the old single-column atr_14 canary that would miss
        # partial-writes (e.g. macd populated but rsi_14 NULL).
        sql, params = qm.call_args[0]
        assert 'num_nulls(' in sql
        assert 'atr_14' in sql       # part of the OR-list
        assert 'rsi_14' in sql       # part of the OR-list
        assert 'macd' in sql         # part of the OR-list
        assert 'strat_candle' in sql # strat included too
        assert 'CURRENT_DATE' in sql
        assert params == {'d': 7}

    def test_gap_check_covers_every_derived_column(self):
        """Regression guard: the set of columns in the gap-check SQL
        must include every column the compute path persists. If a
        future indicator is added to DAILY_INDICATOR_TO_SQL_COLUMN
        but not surfaced to _DERIVED_COLS_FOR_GAP_CHECK, partial
        writes for the new column will be silently ignored."""
        from gcp.database import DAILY_INDICATOR_TO_SQL_COLUMN
        for sql_col in DAILY_INDICATOR_TO_SQL_COLUMN.values():
            assert sql_col in mod._DERIVED_COLS_FOR_GAP_CHECK, (
                f"{sql_col!r} is in DAILY_INDICATOR_TO_SQL_COLUMN but "
                "missing from _DERIVED_COLS_FOR_GAP_CHECK — partial "
                "writes for this column will not trigger a daily-mode "
                "re-compute."
            )

    def test_mode_daily_empty_when_no_gaps(self):
        with patch.object(mod, 'query_to_dataframe', return_value=pd.DataFrame()):
            assert mod._tickers_with_gaps(7) == []

    def test_mode_full_returns_all_tickers(self):
        with patch.object(mod, 'query_to_dataframe',
                          return_value=pd.DataFrame({'ticker': ['SPY', 'IWM', 'QQQ']})):
            assert mod._all_tickers() == ['SPY', 'IWM', 'QQQ']


class TestComputePass:
    def test_produces_indicator_rows_from_full_history(self):
        bars = _synth_bars(60)
        rows = mod._build_indicator_rows('TEST', bars)
        # Should produce a row per bar where indicators became defined.
        # atr_14 needs 14 bars; rsi_14 also ~14; we expect ~46 useful rows.
        assert len(rows) >= 40
        # Every row must carry the PK + at least one indicator column
        for r in rows:
            assert r['ticker'] == 'TEST'
            assert isinstance(r['date'], date)
            indicator_cols = set(r.keys()) - {'ticker', 'date'}
            assert len(indicator_cols) >= 1
        # And atr_14 should be present on the later rows (the early ones
        # haven't accumulated enough history yet).
        last_row = rows[-1]
        assert 'atr_14' in last_row
        assert last_row['atr_14'] > 0

    def test_empty_history_returns_empty(self):
        assert mod._build_indicator_rows('TEST', pd.DataFrame()) == []

    def test_single_bar_returns_empty(self):
        bars = _synth_bars(1)
        assert mod._build_indicator_rows('TEST', bars) == []


class TestBackfillTicker:
    def test_backfill_ticker_upserts_rows(self):
        bars = _synth_bars(40)
        with patch.object(mod, '_full_history', return_value=bars), \
             patch.object(mod, 'upsert_dataframe') as ups:
            n = mod.backfill_ticker('SPY')
        assert n > 0
        ups.assert_called_once()
        df_written, table, pk = ups.call_args[0]
        assert table == 'market_data_daily'
        assert pk == ['ticker', 'date']
        assert all(df_written['ticker'] == 'SPY')

    def test_backfill_ticker_skips_when_empty(self):
        with patch.object(mod, '_full_history', return_value=pd.DataFrame()), \
             patch.object(mod, 'upsert_dataframe') as ups:
            n = mod.backfill_ticker('XYZ')
        assert n == 0
        ups.assert_not_called()
