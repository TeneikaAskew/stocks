"""Tests for the backtest-pipeline Cloud SQL table migration.

The backtest pipeline used to hand off between its "simulate" and
"report" stages via CSV files in data/backtest_results/. That seam is
now three Cloud SQL tables: backtest_trades, backtest_sweeps,
backtest_reports.

These tests pin the table-write / table-read logic added to:
  - scripts/run_backtest.py:persist_trades
  - scripts/run_timeframe_sweep.py:persist_sweeps
  - scripts/generate_backtest_report.py:load_trades_from_table,
    load_sweeps_from_table, compute_aggregate_metrics, persist_report

Cloud SQL is fully mocked (patch.object on the db helpers) — no live
database is needed, matching the pattern in
tests/test_backfill_daily_indicators.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

import gcp.database as db
import scripts.run_backtest as rb
import scripts.run_timeframe_sweep as rs
import scripts.generate_backtest_report as gr


# ── fixtures ──────────────────────────────────────────────────────────

RUN_ID = "11111111-2222-3333-4444-555555555555"


def _synth_trades(n: int = 6) -> pd.DataFrame:
    """A DataFrame shaped like BacktestResult.to_dataframe()."""
    base = datetime(2025, 1, 2, 9, 31)
    rows = []
    for i in range(n):
        entry = base + timedelta(minutes=i * 15)
        rows.append({
            "entry_time": entry,
            "exit_time": entry + timedelta(minutes=8),
            "direction": "CALL" if i % 2 == 0 else "PUT",
            "entry_price": 100.0 + i,
            "exit_price": 100.5 + i,
            "exit_reason": "target" if i % 3 else "stop_loss",
            "base_score": 3,
            "strat_bonus": 1,
            "total_score": 4,
            "position_size": 1.0,
            "return_pct": 0.004 if i % 3 else -0.003,
            "mae": -0.002,
            "mfe": 0.006,
            "ftfc_score": 0.5,
            "orb_trend": 1,
            "conditions": "rsi, ema, vwap",
        })
    return pd.DataFrame(rows)


def _synth_sweep_rows() -> list[dict]:
    """Rows shaped like run_timeframe_sweep.result_to_row() + 'type'."""
    return [
        {"label": "1m", "trades": 120, "win_rate": 0.49, "avg_win": 0.004,
         "avg_loss": -0.003, "pf": 1.1, "expectancy": 0.0002, "max_dd": -0.05,
         "sharpe": 0.4, "type": "single"},
        {"label": "1m+15m", "trades": 60, "win_rate": 0.58, "avg_win": 0.005,
         "avg_loss": -0.003, "pf": 1.9, "expectancy": 0.0011, "max_dd": -0.03,
         "sharpe": 1.4, "type": "combo"},
    ]


# ── persist_trades (run_backtest.py) ──────────────────────────────────

class TestPersistTrades:
    def test_writes_to_backtest_trades_table(self):
        trades = _synth_trades(6)
        with patch.object(db, "upsert_dataframe", return_value=6) as ups:
            n = rb.persist_trades(trades, RUN_ID, "SPY", use_strat=True)
        assert n == 6
        ups.assert_called_once()
        df_written, = ups.call_args[0][:1]
        kwargs = ups.call_args[1]
        assert kwargs["table"] == "backtest_trades"
        assert kwargs["conflict_cols"] == ["run_id", "ticker", "mode", "trade_seq"]

    def test_tags_every_row_with_run_grouping_columns(self):
        trades = _synth_trades(5)
        with patch.object(db, "upsert_dataframe", return_value=5) as ups:
            rb.persist_trades(trades, RUN_ID, "IWM", use_strat=False)
        df = ups.call_args[0][0]
        assert (df["run_id"] == RUN_ID).all()
        assert (df["ticker"] == "IWM").all()
        assert (df["use_strat"] == False).all()  # noqa: E712
        assert (df["mode"] == "base").all()

    def test_strat_mode_label(self):
        trades = _synth_trades(3)
        with patch.object(db, "upsert_dataframe", return_value=3) as ups:
            rb.persist_trades(trades, RUN_ID, "QQQ", use_strat=True)
        df = ups.call_args[0][0]
        assert (df["mode"] == "strat").all()
        assert (df["use_strat"] == True).all()  # noqa: E712

    def test_trade_seq_is_zero_based_and_unique(self):
        """trade_seq completes the natural key so a same-run-id re-run
        converges via ON CONFLICT rather than appending duplicates."""
        trades = _synth_trades(7)
        with patch.object(db, "upsert_dataframe", return_value=7) as ups:
            rb.persist_trades(trades, RUN_ID, "SPY", use_strat=True)
        df = ups.call_args[0][0]
        assert list(df["trade_seq"]) == [0, 1, 2, 3, 4, 5, 6]
        assert df["trade_seq"].is_unique

    def test_original_trade_columns_preserved(self):
        """The BacktestResult.to_dataframe() columns must survive intact —
        only the run grouping columns are prepended."""
        trades = _synth_trades(4)
        with patch.object(db, "upsert_dataframe", return_value=4) as ups:
            rb.persist_trades(trades, RUN_ID, "SPY", use_strat=True)
        df = ups.call_args[0][0]
        for col in ("entry_time", "exit_time", "direction", "return_pct",
                    "exit_reason", "mae", "mfe", "ftfc_score", "conditions"):
            assert col in df.columns

    def test_db_failure_propagates(self):
        """No silent fallback: a Cloud SQL write failure must raise
        (CLAUDE.md §3.7 — data-access code re-raises)."""
        trades = _synth_trades(3)
        with patch.object(db, "upsert_dataframe",
                          side_effect=RuntimeError("cloud sql down")):
            with pytest.raises(RuntimeError, match="cloud sql down"):
                rb.persist_trades(trades, RUN_ID, "SPY", use_strat=True)


# ── persist_sweeps (run_timeframe_sweep.py) ───────────────────────────

class TestPersistSweeps:
    def test_writes_to_backtest_sweeps_table(self):
        with patch.object(db, "upsert_dataframe", return_value=2) as ups:
            n = rs.persist_sweeps(_synth_sweep_rows(), RUN_ID, "SPY")
        assert n == 2
        kwargs = ups.call_args[1]
        assert kwargs["table"] == "backtest_sweeps"
        assert kwargs["conflict_cols"] == ["run_id", "ticker", "label"]

    def test_type_column_renamed_to_sweep_type(self):
        """The in-memory dict uses 'type'; the table column is
        'sweep_type' (SQL reserved-ish name avoidance)."""
        with patch.object(db, "upsert_dataframe", return_value=2) as ups:
            rs.persist_sweeps(_synth_sweep_rows(), RUN_ID, "SPY")
        df = ups.call_args[0][0]
        assert "sweep_type" in df.columns
        assert "type" not in df.columns
        assert set(df["sweep_type"]) == {"single", "combo"}

    def test_tags_run_and_ticker(self):
        with patch.object(db, "upsert_dataframe", return_value=2) as ups:
            rs.persist_sweeps(_synth_sweep_rows(), RUN_ID, "IWM")
        df = ups.call_args[0][0]
        assert (df["run_id"] == RUN_ID).all()
        assert (df["ticker"] == "IWM").all()

    def test_empty_rows_writes_nothing(self):
        with patch.object(db, "upsert_dataframe") as ups:
            n = rs.persist_sweeps([], RUN_ID, "SPY")
        assert n == 0
        ups.assert_not_called()

    def test_db_failure_propagates(self):
        with patch.object(db, "upsert_dataframe",
                          side_effect=RuntimeError("cloud sql down")):
            with pytest.raises(RuntimeError, match="cloud sql down"):
                rs.persist_sweeps(_synth_sweep_rows(), RUN_ID, "SPY")


# ── load_trades_from_table (generate_backtest_report.py) ──────────────

def _table_trades(run_id: str = RUN_ID, n: int = 6) -> pd.DataFrame:
    """A DataFrame shaped like a SELECT * FROM backtest_trades result."""
    df = _synth_trades(n)
    df.insert(0, "run_id", run_id)
    df.insert(1, "ticker", "SPY")
    df.insert(2, "use_strat", True)
    df.insert(3, "mode", "strat")
    df.insert(4, "trade_seq", range(n))
    df["created_at"] = datetime(2025, 1, 2, 16, 0)
    return df


class TestLoadTradesFromTable:
    def test_run_id_filter_builds_scoped_query(self):
        with patch.object(gr, "query_to_dataframe",
                          return_value=_table_trades()) as q:
            out = gr.load_trades_from_table("SPY", "strat", RUN_ID)
        sql, params = q.call_args[0]
        assert "run_id = :run_id" in sql
        assert params == {"ticker": "SPY", "mode": "strat", "run_id": RUN_ID}
        assert out is not None and len(out) == 6

    def test_no_run_id_selects_newest_run(self):
        with patch.object(gr, "query_to_dataframe",
                          return_value=_table_trades()) as q:
            gr.load_trades_from_table("SPY", "base", None)
        sql, params = q.call_args[0]
        assert "created_at DESC" in sql
        assert "run_id" not in params

    def test_enriches_with_derived_columns(self):
        """Table reads must produce the same shape lib/insights expects:
        duration_min, won, return_bps — identical to the CSV path."""
        with patch.object(gr, "query_to_dataframe",
                          return_value=_table_trades()):
            out = gr.load_trades_from_table("SPY", "strat", RUN_ID)
        for col in ("duration_min", "won", "return_bps"):
            assert col in out.columns
        assert out["won"].dtype == bool

    def test_no_rows_returns_none(self):
        """None (not empty DF) distinguishes 'no data' from 'zero trades'."""
        with patch.object(gr, "query_to_dataframe",
                          return_value=pd.DataFrame()):
            assert gr.load_trades_from_table("SPY", "strat", RUN_ID) is None


class TestLoadSweepsFromTable:
    def _table_sweeps(self) -> pd.DataFrame:
        df = pd.DataFrame(_synth_sweep_rows())
        df = df.rename(columns={"type": "sweep_type"})
        df.insert(0, "run_id", RUN_ID)
        df.insert(1, "ticker", "SPY")
        df["created_at"] = datetime(2025, 1, 2, 16, 0)
        return df

    def test_renames_sweep_type_back_to_type(self):
        """lib/insights' sweep functions filter on a 'type' column."""
        with patch.object(gr, "query_to_dataframe",
                          return_value=self._table_sweeps()):
            out = gr.load_sweeps_from_table("SPY", RUN_ID)
        assert "type" in out.columns
        assert "sweep_type" not in out.columns
        assert set(out["type"]) == {"single", "combo"}

    def test_run_id_filter(self):
        with patch.object(gr, "query_to_dataframe",
                          return_value=self._table_sweeps()) as q:
            gr.load_sweeps_from_table("SPY", RUN_ID)
        sql, params = q.call_args[0]
        assert "run_id = :run_id" in sql
        assert params["run_id"] == RUN_ID

    def test_no_rows_returns_none(self):
        with patch.object(gr, "query_to_dataframe",
                          return_value=pd.DataFrame()):
            assert gr.load_sweeps_from_table("SPY", None) is None


# ── compute_aggregate_metrics ─────────────────────────────────────────

class TestComputeAggregateMetrics:
    def test_pools_across_tickers(self):
        spy = gr._enrich_trades(_synth_trades(6))
        iwm = gr._enrich_trades(_synth_trades(4))
        m = gr.compute_aggregate_metrics({"SPY": spy, "IWM": iwm})
        assert m["total_trades"] == 10
        assert 0.0 <= m["win_rate"] <= 1.0
        assert m["expectancy_pct"] is not None

    def test_empty_input_returns_none_not_zero(self):
        """No silent zero — a missing metric is None/NaN, not 0
        (CLAUDE.md §3.7: 0 must never be ambiguous with missing)."""
        m = gr.compute_aggregate_metrics({})
        assert m["total_trades"] == 0
        assert m["win_rate"] is None
        assert m["expectancy_pct"] is None
        assert m["sharpe"] is None

    def test_win_rate_matches_manual_count(self):
        trades = gr._enrich_trades(_synth_trades(6))
        m = gr.compute_aggregate_metrics({"SPY": trades})
        expected_wr = (trades["return_pct"] > 0).mean()
        assert m["win_rate"] == pytest.approx(expected_wr)


# ── persist_report ────────────────────────────────────────────────────

class TestPersistReport:
    def test_inserts_into_backtest_reports(self):
        metrics = {"total_trades": 10, "win_rate": 0.55,
                   "expectancy_pct": 0.0007, "sharpe": 1.2}
        with patch.object(gr, "execute_sql") as ex:
            gr.persist_report(RUN_ID, ["SPY", "IWM"], "# Report\n", metrics)
        ex.assert_called_once()
        sql, params = ex.call_args[0]
        assert "INSERT INTO backtest_reports" in sql
        assert "ON CONFLICT (run_id) DO UPDATE" in sql
        assert params["run_id"] == RUN_ID
        assert params["tickers"] == ["SPY", "IWM"]
        assert params["report_md"] == "# Report\n"
        assert params["total_trades"] == 10

    def test_idempotent_on_rerun(self):
        """run_id is the PK + ON CONFLICT DO UPDATE — re-running the
        report stage for the same pipeline run overwrites, not errors."""
        metrics = {"total_trades": 0, "win_rate": None,
                   "expectancy_pct": None, "sharpe": None}
        with patch.object(gr, "execute_sql") as ex:
            gr.persist_report(RUN_ID, ["SPY"], "# md\n", metrics)
        sql = ex.call_args[0][0]
        assert "ON CONFLICT (run_id) DO UPDATE" in sql


# ── end-to-end shape: build_report reads tables ───────────────────────

class TestBuildReportFromTables:
    def test_build_report_uses_tables_when_cloud_sql_configured(self):
        """build_report must route through the table-loaders, not the
        CSV globbers, when Cloud SQL is configured."""
        trades = _table_trades()
        with patch.object(gr, "is_cloud_sql_configured", return_value=True), \
             patch.object(gr, "load_trades_from_table") as lt, \
             patch.object(gr, "load_sweeps_from_table", return_value=None), \
             patch.object(gr, "find_trade_csv") as csv_finder:
            lt.return_value = gr._enrich_trades(_synth_trades(6))
            report = gr.build_report(["SPY"], run_id=RUN_ID)
        # CSV discovery must NOT be touched on the Cloud SQL path.
        csv_finder.assert_not_called()
        assert "Backtest Results" in report

    def test_build_report_falls_back_to_csv_when_not_configured(self):
        """The CSV path is the offline/local-dev fallback only."""
        with patch.object(gr, "is_cloud_sql_configured", return_value=False), \
             patch.object(gr, "find_trade_csv", return_value=None), \
             patch.object(gr, "find_sweep_csv", return_value=None):
            report = gr.build_report(["SPY"], run_id=None)
        assert "*No backtest data found.*" in report
