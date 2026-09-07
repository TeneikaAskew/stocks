"""TradeLogger's default readers must exclude non-live trade rows.

Codex on #1022: trades.run_kind was added so the 412 simulated rows
written by the deleted scripts/backfill_signals.py can be marked
'backfill', and the API readers were filtered, but gcp/weekend_review.py
reads through TradeLogger.get_weekly_trades(), whose SQL selected every
row, so the Discord weekly summary still counted simulated trades. The
three Cloud SQL readers now default to run_kind='live' (None reads every
kind), matching DataLoader.load_trades.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from gcp.trade_logger import TradeLogger


def _capture(method, *args, **kwargs):
    seen: list[tuple[str, dict | None]] = []

    def fake_query(sql, params=None):
        seen.append((" ".join(sql.split()), params))
        return pd.DataFrame({"trade_id": [1]})

    with patch("gcp.trade_logger._cloud_sql_active", return_value=True), \
         patch("gcp.database.query_to_dataframe", fake_query):
        out = method(*args, **kwargs)
    assert len(seen) == 1, seen
    assert len(out) == 1
    return seen[0]


def test_daily_weekly_and_all_readers_restrict_to_live_by_default(tmp_path):
    tl = TradeLogger(output_dir=str(tmp_path))
    for call in (
        lambda: tl.get_daily_trades(date(2026, 4, 1)),
        lambda: tl.get_weekly_trades(date(2026, 4, 7)),
        lambda: tl.get_all_trades(),
    ):
        sql, params = _capture(call)
        assert "run_kind = :rk" in sql, sql
        assert params["rk"] == "live", params


def test_readers_can_opt_into_every_run_kind(tmp_path):
    tl = TradeLogger(output_dir=str(tmp_path))
    for call in (
        lambda: tl.get_daily_trades(date(2026, 4, 1), run_kind=None),
        lambda: tl.get_weekly_trades(date(2026, 4, 7), run_kind=None),
        lambda: tl.get_all_trades(run_kind=None),
    ):
        sql, params = _capture(call)
        assert "run_kind" not in sql, sql
        assert not params or "rk" not in params


def test_weekend_review_reads_live_trades_only():
    """gcp/weekend_review.py takes the default, so the summary excludes
    backfill and replay rows."""
    import inspect

    from gcp import weekend_review

    src = inspect.getsource(weekend_review.generate_weekly_review)
    assert "get_weekly_trades()" in src, "the review must take the live default"


def _write_parquet(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_parquet_fallback_applies_the_same_run_kind_filter(tmp_path):
    """Codex on #1022 (round 14): with Cloud SQL unavailable (or the live
    query empty) the readers fall through to the Parquet files, which
    log_trade() writes for every kind, so the weekend review could still
    count replay or backfill rows. The fallback frames are filtered too; a
    file written before the column existed holds live monitor rows."""
    tl = TradeLogger(output_dir=str(tmp_path))
    d1, d2 = date(2026, 4, 1), date(2026, 4, 2)
    _write_parquet(tl._daily_file(d1), [
        {"trade_id": 1, "run_kind": "live"},
        {"trade_id": 2, "run_kind": "replay"},
        {"trade_id": 3, "run_kind": "backfill"},
    ])
    _write_parquet(tl._daily_file(d2), [{"trade_id": 4}])      # pre-column file
    with patch("gcp.trade_logger._cloud_sql_active", return_value=False):
        assert sorted(tl.get_daily_trades(d1)["trade_id"]) == [1]
        assert sorted(tl.get_daily_trades(d1, run_kind="replay")["trade_id"]) == [2]
        assert sorted(tl.get_daily_trades(d1, run_kind=None)["trade_id"]) == [1, 2, 3]
        assert sorted(tl.get_daily_trades(d2)["trade_id"]) == [4], "no column means live"
        assert tl.get_daily_trades(d2, run_kind="replay").empty
        assert sorted(tl.get_weekly_trades(d2)["trade_id"]) == [1, 4]
        assert sorted(tl.get_all_trades()["trade_id"]) == [1, 4]
        assert sorted(tl.get_all_trades(run_kind=None)["trade_id"]) == [1, 2, 3, 4]


def test_empty_live_query_falls_through_to_filtered_parquet(tmp_path):
    tl = TradeLogger(output_dir=str(tmp_path))
    d1 = date(2026, 4, 1)
    _write_parquet(tl._daily_file(d1), [
        {"trade_id": 1, "run_kind": "live"}, {"trade_id": 2, "run_kind": "replay"}])
    with patch("gcp.trade_logger._cloud_sql_active", return_value=True), \
         patch("gcp.database.query_to_dataframe", lambda sql, params=None: pd.DataFrame()):
        assert sorted(tl.get_daily_trades(d1)["trade_id"]) == [1]


_REAL_COLUMNS = ['ticker', 'direction', 'entry_time', 'entry_price', 'signal_strength',
                 'total_score', 'position_size', 'conditions_met', 'trade_date']


def _real_row(ticker, **extra):
    row = {'ticker': ticker, 'direction': 'CALL', 'entry_time': '2026-09-07T14:31:00',
           'entry_price': 100.0, 'signal_strength': 6.0, 'total_score': 6, 'position_size': 1.0,
           'conditions_met': 'x', 'trade_date': '2026-09-07'}
    row.update(extra)
    return row


def test_fallback_handles_the_real_nine_column_file_and_a_mixed_file_row_by_row(tmp_path):
    """Internal review of round 14: production Parquet files carry exactly
    these nine columns (data/trades/2026-09-07.parquet, 523 rows) and the
    only writer is the live monitor's fire_alert, which now stamps
    run_kind; rows from before the stamp carry none. The rule is row-level:
    a null run_kind reads as live, so a mixed file (pre-stamp rows appended
    to by stamped rows) keeps its earlier rows instead of dropping them."""
    tl = TradeLogger(output_dir=str(tmp_path))
    d1, d2 = date(2026, 9, 6), date(2026, 9, 7)
    _write_parquet(tl._daily_file(d1), [_real_row('SPY'), _real_row('IWM')])
    pd.DataFrame([_real_row('QQQ')]).to_parquet(tl._daily_file(d2), index=False)
    tl.log_trade(_real_row('DIA', run_kind='live', trade_date='2026-09-07'))
    tl.log_trade(_real_row('XLF', run_kind='replay', trade_date='2026-09-07'))
    mixed = pd.read_parquet(tl._daily_file(d2))
    assert list(mixed['run_kind'].isna()) == [True, False, False], "the pre-stamp row is null, not dropped"
    with patch("gcp.trade_logger._cloud_sql_active", return_value=False):
        assert sorted(tl.get_daily_trades(d1)['ticker']) == ['IWM', 'SPY']
        assert sorted(tl.get_daily_trades(d2)['ticker']) == ['DIA', 'QQQ']
        assert sorted(tl.get_daily_trades(d2, run_kind='replay')['ticker']) == ['XLF']
        assert sorted(tl.get_weekly_trades(d2)['ticker']) == ['DIA', 'IWM', 'QQQ', 'SPY']
        empty = tl.get_all_trades(run_kind='backfill')
        assert empty.empty and 'ticker' in empty.columns, "an empty result keeps the schema"


def test_the_monitor_stamps_run_kind_on_every_logged_trade():
    """So the Parquet files carry provenance from now on and the null-as-live
    rule shrinks to the files written before this change."""
    import inspect

    from gcp import signal_monitor

    src = inspect.getsource(signal_monitor.SignalMonitor._persist_signal_alert)
    block = src[src.index("trade_data = {"):src.index("TradeLogger().log_trade(trade_data)")]
    assert "'run_kind': 'live'" in block


def test_the_trade_parquet_files_have_exactly_one_writer():
    """Tripwire for _filter_run_kind's null-as-live rule (internal review of
    #1022, fallback guard). A null run_kind in a Parquet row reads as 'live'
    ONLY because every row in data/trades/*.parquet was written by
    TradeLogger.log_trade from the monitor's _persist_signal_alert, which now
    stamps run_kind. A second writer of those files, or a second caller of
    log_trade, invalidates that reading, so this test fails the moment one
    appears and the rule has to become explicit provenance instead."""
    import ast
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    tree = ast.parse((repo / "gcp/trade_logger.py").read_text())
    writers = sorted(
        f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
        and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "to_parquet" for n in ast.walk(f)))
    assert writers == ["log_trade"], writers

    other_writers, callers = [], []
    for area in ("lib", "gcp", "scripts", "platform/api"):
        for path in sorted((repo / area).rglob("*.py")):
            rel = path.relative_to(repo).as_posix()
            text = path.read_text()
            if rel != "gcp/trade_logger.py" and "to_parquet(" in text \
                    and re.search(r"\btrades_dir\b|\b_daily_file\b|data/trades|TradeLogger", text):
                other_writers.append(rel)
            if re.search(r"\.log_trade\(", text):
                callers.append(rel)
    assert other_writers == [], other_writers
    assert callers == ["gcp/signal_monitor.py"], callers
