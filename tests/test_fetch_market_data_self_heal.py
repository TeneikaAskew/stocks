"""Hermetic tests for the self-healing indicator chain and sharded
backfill in gcp/fetchers/fetch_market_data.py.

Target paths:
  - _indicator_coverage(ticker)
        Aggregates COUNT(*) and COUNT(atr_14)/COUNT(*) ratios for one
        ticker. Used as the trigger for full-range recompute.
  - compute_and_upsert_daily_indicators(ticker, fetch_date)
        The decision tree wired in front of the existing single-row
        upsert: when atr_coverage < 0.95, call
        compute_indicators_for_full_range; otherwise skip the recompute.
  - _run_backfill() shard slicing — task_index/task_count selects
        every Nth ticker.

All DB / AV interactions are mocked so the suite is hermetic and runs
in microseconds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ────────────────────────────────────────────────────────────
# _indicator_coverage
# ────────────────────────────────────────────────────────────

class TestIndicatorCoverage:
    def test_returns_zero_for_empty_df(self):
        from gcp.fetchers import fetch_market_data
        with patch('gcp.database.query_to_dataframe',
                   return_value=pd.DataFrame()):
            cov = fetch_market_data._indicator_coverage('TEST')
        assert cov == {'bar_count': 0, 'atr_coverage': 0.0}

    def test_full_coverage(self):
        from gcp.fetchers import fetch_market_data
        df = pd.DataFrame([{'bar_count': 250, 'atr_coverage': 1.0}])
        with patch('gcp.database.query_to_dataframe', return_value=df):
            cov = fetch_market_data._indicator_coverage('AVGO')
        assert cov['bar_count'] == 250
        assert cov['atr_coverage'] == 1.0

    def test_partial_coverage(self):
        """The post-#239 bug: 800 bars but only ~3% have atr_14."""
        from gcp.fetchers import fetch_market_data
        df = pd.DataFrame([{'bar_count': 800, 'atr_coverage': 0.025}])
        with patch('gcp.database.query_to_dataframe', return_value=df):
            cov = fetch_market_data._indicator_coverage('MCK')
        assert cov['bar_count'] == 800
        assert cov['atr_coverage'] == 0.025


# ────────────────────────────────────────────────────────────
# compute_and_upsert_daily_indicators decision tree
# ────────────────────────────────────────────────────────────

@pytest.fixture
def fake_full_indicator_df():
    """50 bars of OHLC — enough for add_all_indicators to populate atr_14."""
    rows = []
    base = 100.0
    for i in range(50):
        rows.append({
            'date': pd.Timestamp(f'2026-0{1 + i // 30}-{1 + (i % 30):02d}').date(),
            'Open': base + i * 0.1,
            'High': base + i * 0.1 + 1,
            'Low': base + i * 0.1 - 1,
            'Close': base + i * 0.1 + 0.5,
            'Volume': 1_000_000,
        })
    return pd.DataFrame(rows)


class TestComputeAndUpsertSelfHeal:
    """Verifies the decision tree:
       coverage < threshold → triggers full-range recompute first
       coverage >= threshold → no recompute, just single-row upsert
       bar_count < 2 → skip recompute (too sparse to be a gap)
    """

    def _patch_db_and_classifier(self, daily_df, coverage):
        """Common patches: fake DB and a pass-through StratClassifier so
        the test isn't sensitive to live indicator math."""
        coverage_patch = patch(
            'gcp.fetchers.fetch_market_data._indicator_coverage',
            return_value=coverage,
        )
        # Mock all database operations
        query_patch = patch(
            'gcp.database.query_to_dataframe',
            return_value=daily_df,
        )
        upsert_patch = patch('gcp.database.upsert_dataframe')
        return coverage_patch, query_patch, upsert_patch

    def test_coverage_above_threshold_skips_full_recompute(self, fake_full_indicator_df):
        """atr_coverage = 0.99 → no full-range recompute."""
        from gcp.fetchers import fetch_market_data
        coverage = {'bar_count': 250, 'atr_coverage': 0.99}
        coverage_patch, query_patch, upsert_patch = (
            self._patch_db_and_classifier(fake_full_indicator_df, coverage)
        )

        with coverage_patch, query_patch, upsert_patch, \
             patch('gcp.backfill_ticker.compute_indicators_for_full_range') as m_full:
            fetch_market_data.compute_and_upsert_daily_indicators(
                'AVGO', '2026-05-04',
            )

        assert m_full.call_count == 0, \
            "should NOT call full-range recompute when coverage is fine"

    def test_coverage_below_threshold_triggers_recompute(self, fake_full_indicator_df):
        """atr_coverage = 0.10 → MUST call compute_indicators_for_full_range."""
        from gcp.fetchers import fetch_market_data
        coverage = {'bar_count': 800, 'atr_coverage': 0.10}
        coverage_patch, query_patch, upsert_patch = (
            self._patch_db_and_classifier(fake_full_indicator_df, coverage)
        )

        with coverage_patch, query_patch, upsert_patch, \
             patch('gcp.backfill_ticker.compute_indicators_for_full_range') as m_full:
            fetch_market_data.compute_and_upsert_daily_indicators(
                'MCK', '2026-05-04',
            )

        assert m_full.call_count == 1
        assert m_full.call_args[0][0] == 'MCK'

    def test_zero_bars_skips_recompute(self, fake_full_indicator_df):
        """bar_count == 0 → recompute would have nothing to operate on,
        and the existing 'len(df) < 2' guard would short-circuit anyway."""
        from gcp.fetchers import fetch_market_data
        # Empty daily query — still triggers the early-return below the
        # self-heal block. Coverage check should also short-circuit.
        coverage = {'bar_count': 0, 'atr_coverage': 0.0}
        coverage_patch, query_patch, upsert_patch = (
            self._patch_db_and_classifier(pd.DataFrame(), coverage)
        )

        with coverage_patch, query_patch, upsert_patch, \
             patch('gcp.backfill_ticker.compute_indicators_for_full_range') as m_full:
            fetch_market_data.compute_and_upsert_daily_indicators(
                'NEWBIE', '2026-05-04',
            )

        assert m_full.call_count == 0

    def test_recompute_failure_does_not_crash_pipeline(self, fake_full_indicator_df):
        """If compute_indicators_for_full_range raises, log + continue —
        the daily fetcher must still write today's row."""
        from gcp.fetchers import fetch_market_data
        coverage = {'bar_count': 800, 'atr_coverage': 0.10}
        coverage_patch, query_patch, upsert_patch = (
            self._patch_db_and_classifier(fake_full_indicator_df, coverage)
        )

        with coverage_patch, query_patch, upsert_patch, \
             patch('gcp.backfill_ticker.compute_indicators_for_full_range',
                   side_effect=RuntimeError('simulated DB error')):
            # Should not raise.
            fetch_market_data.compute_and_upsert_daily_indicators(
                'MCK', '2026-05-04',
            )


# ────────────────────────────────────────────────────────────
# Sharded backfill — task_index slicing
# ────────────────────────────────────────────────────────────

class TestShardedBackfill:
    def _fake_targets(self, n: int):
        """N tickers, all needing 'full' pulls (bar_count=0 → outputsize=full)."""
        return [(f'T{i:03d}', 0, None) for i in range(n)]

    def _patch_run_backfill_io(self, targets):
        """Patch _backfill_targets, AV fetcher (returns empty), upsert,
        is_cloud_sql_configured, and the API key check."""
        targets_patch = patch(
            'gcp.fetchers.fetch_market_data._backfill_targets',
            return_value=targets,
        )
        av_patch = patch(
            'gcp.fetchers.fetch_market_data._av_get_full_daily_series',
            return_value=pd.DataFrame(),
        )
        upsert_patch = patch('gcp.database.upsert_dataframe')
        sql_cfg_patch = patch(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            return_value=True,
        )
        return targets_patch, av_patch, upsert_patch, sql_cfg_patch

    def test_no_sharding_processes_all(self, monkeypatch):
        """task_count=1 (default): every ticker is in this task's pending list."""
        from gcp.fetchers import fetch_market_data
        monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake')
        monkeypatch.delenv('CLOUD_RUN_TASK_COUNT', raising=False)
        monkeypatch.delenv('CLOUD_RUN_TASK_INDEX', raising=False)

        targets = self._fake_targets(8)
        captured = []

        def fake_av(ticker, *_a, **_k):
            captured.append(ticker)
            return pd.DataFrame()

        targets_patch, _, upsert_patch, sql_cfg_patch = (
            self._patch_run_backfill_io(targets)
        )
        with targets_patch, upsert_patch, sql_cfg_patch, \
             patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
                   side_effect=fake_av), \
             patch('time.sleep'):
            fetch_market_data._run_backfill()
        assert captured == [t for t, _, _ in targets]

    def test_shard_2_of_4_picks_every_4th_starting_at_offset_2(self, monkeypatch):
        """task_count=4, task_index=2 → indices 2, 6 (out of 8)."""
        from gcp.fetchers import fetch_market_data
        monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake')
        monkeypatch.setenv('CLOUD_RUN_TASK_COUNT', '4')
        monkeypatch.setenv('CLOUD_RUN_TASK_INDEX', '2')

        targets = self._fake_targets(8)
        captured = []

        def fake_av(ticker, *_a, **_k):
            captured.append(ticker)
            return pd.DataFrame()

        targets_patch, _, upsert_patch, sql_cfg_patch = (
            self._patch_run_backfill_io(targets)
        )
        with targets_patch, upsert_patch, sql_cfg_patch, \
             patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
                   side_effect=fake_av), \
             patch('time.sleep'):
            fetch_market_data._run_backfill()
        assert captured == ['T002', 'T006']

    def test_shard_partition_disjoint_and_complete(self, monkeypatch):
        """Across all 4 shards, every ticker is processed exactly once."""
        from gcp.fetchers import fetch_market_data
        monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake')

        targets = self._fake_targets(10)
        seen_per_shard: dict[int, list[str]] = {}

        for shard_idx in range(4):
            monkeypatch.setenv('CLOUD_RUN_TASK_COUNT', '4')
            monkeypatch.setenv('CLOUD_RUN_TASK_INDEX', str(shard_idx))
            captured: list[str] = []

            def fake_av(ticker, *_a, **_k):
                captured.append(ticker)
                return pd.DataFrame()

            targets_patch, _, upsert_patch, sql_cfg_patch = (
                self._patch_run_backfill_io(targets)
            )
            with targets_patch, upsert_patch, sql_cfg_patch, \
                 patch('gcp.fetchers.fetch_market_data._av_get_full_daily_series',
                       side_effect=fake_av), \
                 patch('time.sleep'):
                fetch_market_data._run_backfill()
            seen_per_shard[shard_idx] = captured

        all_seen = []
        for items in seen_per_shard.values():
            all_seen.extend(items)
        # Every ticker covered exactly once across the union of shards
        assert sorted(all_seen) == sorted(t for t, _, _ in targets)
        # And within a shard, no duplicates
        for items in seen_per_shard.values():
            assert len(items) == len(set(items))
