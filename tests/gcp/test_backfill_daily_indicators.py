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
        assert 'ema_9' in sql        # part of the OR-list
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

    def test_gap_check_is_convergent(self):
        """Regression guard for issue #751: the gap check must only flag
        *healable* gaps, or the nightly self-heal re-processes the same
        tickers forever (2,400-ticker mornings → 3h timeout → daily
        death loop, Aug 4–23 2026)."""
        with patch.object(mod, 'query_to_dataframe',
                          return_value=pd.DataFrame()) as qm:
            mod._tickers_with_gaps(7)
        sql, _params = qm.call_args[0]
        # Same-day partial rows (intraday snapshot writers) are not gaps.
        assert 'm.date < CURRENT_DATE' in sql
        # Rows whose raw OHLCV is null are uncomputable — never flag them.
        assert 'num_nulls(m.open, m.high, m.low, m.close, m.volume) = 0' in sql
        # Warmup gating: a young ticker structurally cannot fill
        # sma_200 / ema_50 / ma_50 — nulls there only count once the
        # ticker has enough bars for the column's window.
        assert f'n_bars >= {mod._WARMUP_200_MIN_BARS}' in sql
        assert f'n_bars >= {mod._WARMUP_50_MIN_BARS}' in sql
        assert f'n_bars >= {mod._WARMUP_SHORT_MIN_BARS}' in sql
        # Warmup thresholds must count only USABLE bars (complete raw
        # OHLCV) — rows the compute path drops can't satisfy a warmup.
        cte = sql.split('SELECT DISTINCT')[0]
        assert 'num_nulls(open, high, low, close, volume) = 0' in cte
        # Formula-domain columns (legitimately NaN on flat/zero-volume
        # stretches — denominator is zero, recompute reproduces the
        # NaN) must never appear in the flag predicate. Live residue
        # 2026-08-24 was exactly bb_pct/rvol/bb_squeeze re-queuing 5
        # tickers forever.
        for col in mod._FORMULA_DOMAIN_COLS:
            assert col not in sql, (
                f"{col} is formula-domain (partial function) — flagging "
                "its NULLs makes the daily self-heal non-convergent"
            )

    def test_warmup_classes_partition_the_gap_columns(self):
        """Every gap-check column must belong to exactly one warmup
        class. A new indicator added to DAILY_INDICATOR_TO_SQL_COLUMN
        lands in the short class by default — correct unless its
        formula needs >50 bars, in which case it must be moved to a
        longer class or it re-creates the issue #751 convergence bug."""
        short = set(mod._WARMUP_SHORT_COLS)
        w50 = set(mod._WARMUP_50_COLS)
        w200 = set(mod._WARMUP_200_COLS)
        formula = set(mod._FORMULA_DOMAIN_COLS)
        classes = [short, w50, w200, formula]
        union = set().union(*classes)
        assert union == set(mod._DERIVED_COLS_FOR_GAP_CHECK)
        assert sum(len(c) for c in classes) == len(union), \
            "warmup/formula classes must be pairwise disjoint"
        # The known long-warmup columns must be gated, not in short.
        assert w200 == {'sma_200'}
        assert w50 == {'ema_50', 'ma_50'}
        # The live-verified non-convergent trio must stay exempt.
        assert {'bb_pct', 'rvol', 'bb_squeeze'} <= formula

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

    def test_null_ohlcv_rows_are_dropped_not_crashing(self):
        """RIVN had None volume on early bars; SPX has None volume on
        every bar (it's an index). Pre-fix, add_all_indicators threw
        TypeError('NoneType' - 'NoneType') and the populator skipped
        the entire ticker. Post-fix, null-OHLCV bars are dropped and
        the rest compute normally."""
        bars = _synth_bars(60)
        # Inject NULL volume on a few early bars
        bars.loc[:5, 'Volume'] = None
        rows = mod._build_indicator_rows('TEST', bars)
        # Should still produce rows — just from the cleaned subset
        assert len(rows) > 30
        # PK + indicators on every row
        for r in rows:
            assert r['ticker'] == 'TEST'

    def test_all_null_ohlcv_returns_empty_with_warning(self):
        """Index-only tickers (no volume) won't have anything to
        compute on. Return empty cleanly, don't crash."""
        bars = _synth_bars(20)
        bars['Volume'] = None
        assert mod._build_indicator_rows('TEST', bars) == []

    def test_strat_combo_nan_string_is_filtered(self):
        """Regression guard for the 2026-05-13 backfill bug where
        ~17% of SPY bars landed as the literal string 'nan' in
        strat_combo because pandas object-dtype Series serialise
        NaN via str() to the 'nan' string. The row-builder MUST
        filter every sentinel for "no value here" — None, NaN,
        and the 'nan' / 'none' / 'X' / '' string sentinels — and
        never write them to the upsert dict."""
        bars = _synth_bars(40)
        rows = mod._build_indicator_rows('TEST', bars)
        for r in rows:
            for col in ('strat_candle', 'strat_combo'):
                if col in r:
                    assert r[col] not in ('', 'X', 'nan', 'none',
                                          'None', 'NaN'), (
                        f"{col}={r[col]!r} is a null-sentinel that "
                        "should have been filtered before upsert"
                    )


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

    def test_recent_days_limits_upsert_to_window(self):
        """I/O-shape guard (CLAUDE.md Rule 0.3, issue #751): daily mode
        computes over the FULL history (cumulative indicators need it)
        but must write back only the recent window — the full-history
        re-upsert (~2,500 rows/ticker × 2,400 tickers ≈ 4.3M rows/night)
        is what blew the 3h task-timeout."""
        bars = _synth_bars(60)
        # Re-date the synthetic bars to end today so a recent window exists.
        today = date.today()
        bars['date'] = [today - timedelta(days=59 - i) for i in range(60)]
        with patch.object(mod, '_full_history', return_value=bars), \
             patch.object(mod, 'upsert_dataframe') as ups:
            n = mod.backfill_ticker('SPY', recent_days=10)
        ups.assert_called_once()
        df_written = ups.call_args[0][0]
        cutoff = today - timedelta(days=10)
        assert (df_written['date'] >= cutoff).all()
        assert 0 < len(df_written) <= 11
        assert n == len(df_written)

    def test_filter_recent_rows_shared_helper(self):
        """--dry-run must preview the same rows the live path writes
        (Codex review on PR #756): both go through _filter_recent_rows."""
        today = date.today()
        rows = [
            {'ticker': 'SPY', 'date': today, 'atr_14': 1.0},
            {'ticker': 'SPY', 'date': today - timedelta(days=3), 'atr_14': 1.0},
            {'ticker': 'SPY', 'date': today - timedelta(days=30), 'atr_14': 1.0},
        ]
        kept = mod._filter_recent_rows(rows, 10)
        assert [r['date'] for r in kept] == [today, today - timedelta(days=3)]
        # None = no filtering (full mode / --tickers recoveries)
        assert mod._filter_recent_rows(rows, None) == rows
        assert mod._filter_recent_rows([], 10) == []

    def test_recent_days_with_only_stale_rows_writes_nothing(self):
        bars = _synth_bars(60)  # dated 2024 — all older than any window
        with patch.object(mod, '_full_history', return_value=bars), \
             patch.object(mod, 'upsert_dataframe') as ups:
            n = mod.backfill_ticker('SPY', recent_days=10)
        assert n == 0
        ups.assert_not_called()


class TestMainWiring:
    def test_daily_mode_runs_pool_with_recent_window(self, monkeypatch):
        """main() must hand every flagged ticker to backfill_ticker with
        the recent-only window (lookback + 5d margin) in daily mode."""
        import sys as _sys
        calls = []

        def fake_backfill(tk, recent_days=None):
            calls.append((tk, recent_days))
            return 3

        monkeypatch.setattr(mod, '_tickers_with_gaps', lambda d: ['AAA', 'BBB'])
        monkeypatch.setattr(mod, 'backfill_ticker', fake_backfill)
        monkeypatch.setattr(mod, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.delenv('BACKFILL_TICKERS', raising=False)
        monkeypatch.setattr(_sys, 'argv', [
            'backfill_daily_indicators', '--mode=daily',
            '--lookback-days', '7', '--workers', '2',
        ])
        assert mod.main() == 0
        assert sorted(calls) == [('AAA', 12), ('BBB', 12)]

    def test_full_mode_keeps_full_history_upsert(self, monkeypatch):
        import sys as _sys
        calls = []

        def fake_backfill(tk, recent_days=None):
            calls.append((tk, recent_days))
            return 1

        monkeypatch.setattr(mod, '_all_tickers', lambda: ['SPY'])
        monkeypatch.setattr(mod, 'backfill_ticker', fake_backfill)
        monkeypatch.setattr(mod, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.delenv('BACKFILL_TICKERS', raising=False)
        monkeypatch.setattr(_sys, 'argv', [
            'backfill_daily_indicators', '--mode=full',
        ])
        assert mod.main() == 0
        assert calls == [('SPY', None)]
