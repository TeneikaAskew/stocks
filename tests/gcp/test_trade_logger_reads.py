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

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from gcp.trade_logger import TradeLogger


def _capture(method, *args, **kwargs):
    seen: list[tuple[str, dict | None]] = []

    def fake_query(sql, params=None):
        seen.append((" ".join(sql.split()), params))
        return pd.DataFrame({"trade_id": [1]})

    with patch("gcp.trade_logger._cloud_sql_active", return_value=True), \
         patch("gcp.database.query_to_dataframe_strict", fake_query):
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

    import re

    src = inspect.getsource(weekend_review.generate_weekly_review)
    calls = re.findall(r"get_weekly_trades\(([^)]*)\)", src)
    assert calls, "the review must read through get_weekly_trades"
    assert all("run_kind" not in c for c in calls), calls


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


def test_an_empty_cloud_sql_answer_is_the_answer_not_a_parquet_fallthrough(tmp_path):
    """Internal review of #1022 (trade-reader round): a successful Cloud SQL
    query that returned no rows fell through to the local Parquet files,
    and the run_kind filter made that branch newly reachable ("there were
    trades, all backfill or replay"). Cloud SQL is the system of record
    (CLAUDE.md 3.7.1); only a FAILED query reaches the Parquet fallback,
    and that path is marked AUDIT-2026-05-13."""
    tl = TradeLogger(output_dir=str(tmp_path))
    d1 = date(2026, 4, 1)
    _write_parquet(tl._daily_file(d1), [
        {"trade_id": 1, "run_kind": "live"}, {"trade_id": 2, "run_kind": "replay"}])
    for f in (tl._daily_file(date(2026, 4, 2)),):
        _write_parquet(f, [{"trade_id": 3, "run_kind": "live"}])
    empty = pd.DataFrame(columns=["trade_id", "run_kind"])
    with patch("gcp.trade_logger._cloud_sql_active", return_value=True), \
         patch("gcp.database.query_to_dataframe_strict", lambda sql, params=None: empty):
        assert tl.get_daily_trades(d1).empty
        assert tl.get_weekly_trades(date(2026, 4, 7)).empty
        assert tl.get_all_trades().empty


def test_a_failed_cloud_sql_query_still_reaches_parquet(tmp_path):
    tl = TradeLogger(output_dir=str(tmp_path))
    d1 = date(2026, 4, 1)
    _write_parquet(tl._daily_file(d1), [
        {"trade_id": 1, "run_kind": "live"}, {"trade_id": 2, "run_kind": "replay"}])

    def _boom(sql, params=None):
        raise RuntimeError("connection lost")

    with patch("gcp.trade_logger._cloud_sql_active", return_value=True), \
         patch("gcp.database.query_to_dataframe_strict", _boom):
        assert sorted(tl.get_daily_trades(d1)["trade_id"]) == [1]


def test_log_trade_requires_provenance(tmp_path):
    """The stamp lives in the writer's contract, not only in the one
    caller: a trade without run_kind is refused, so the Parquet null-as-
    live rule can only ever apply to rows written before the stamp."""
    import pytest
    tl = TradeLogger(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="run_kind"):
        tl.log_trade({"ticker": "SPY", "direction": "CALL", "entry_time": "2026-09-07T14:31:00"})
    assert not list(tmp_path.glob("*.parquet")), "a refused trade writes nothing"


def test_empty_all_trades_keeps_the_union_of_the_files_columns(tmp_path):
    tl = TradeLogger(output_dir=str(tmp_path))
    _write_parquet(tl._daily_file(date(2026, 4, 1)), [{"trade_id": 1, "run_kind": "replay"}])
    _write_parquet(tl._daily_file(date(2026, 4, 2)), [{"trade_id": 2, "run_kind": "replay", "notes": "x"}])
    with patch("gcp.trade_logger._cloud_sql_active", return_value=False):
        out = tl.get_all_trades()
    assert out.empty and set(out.columns) == {"trade_id", "run_kind", "notes"}


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
    # log_trade appends to TODAY's file (the live monitor logs today's
    # trades), so the mixed file is today's; the test must not pin a date.
    d2 = date.today()
    d1 = d2 - timedelta(days=1)
    _write_parquet(tl._daily_file(d1), [_real_row('SPY'), _real_row('IWM')])
    pd.DataFrame([_real_row('QQQ')]).to_parquet(tl._daily_file(d2), index=False)
    tl.log_trade(_real_row('DIA', run_kind='live', trade_date=str(d2)))
    tl.log_trade(_real_row('XLF', run_kind='replay', trade_date=str(d2)))
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


def test_a_failed_cloud_sql_read_reaches_the_parquet_backup(tmp_path, monkeypatch):
    """The three readers' `except` clause and their Parquet fallback were
    both UNREACHABLE for a failed query (Codex on #1022).

    They read through `query_to_dataframe`, which catches the exception and
    returns an empty frame, so the unconditional `return df` above the
    handler answered "no trades" — and the comment claiming only a failed
    query reaches the files was false. The weekend review would report an
    empty week during a database outage while the local backup held live
    rows. Same shape as the kill-switch finding in this round: a swallowing
    helper defeats the caller's error path (CLAUDE.md 3.7.1)."""
    import pandas as pd

    from gcp import trade_logger as tl

    logger = tl.TradeLogger(output_dir=str(tmp_path))
    d = date.today()
    backup = pd.DataFrame([{
        "ticker": "IWM", "direction": "CALL", "entry_time": "09:35",
        "trade_date": str(d), "run_kind": "live",
    }])
    logger._daily_file(d).parent.mkdir(parents=True, exist_ok=True)
    backup.to_parquet(logger._daily_file(d), index=False)

    monkeypatch.setattr(tl, "_cloud_sql_active", lambda: True)

    # Patch the ENGINE, not the helper: patching the helper would make it
    # raise and hide the very swallow under test.
    from gcp import database

    def _refused():
        raise RuntimeError("connection to server ... failed: Connection refused")

    monkeypatch.setattr(database, "get_engine", _refused)

    out = logger.get_daily_trades(d)
    assert not out.empty, "an outage must reach the Parquet backup, not answer 'no trades'"
    assert list(out["ticker"]) == ["IWM"]


def test_the_readers_do_not_read_through_the_swallowing_helper():
    """Pin the class, not the instance: `query_to_dataframe` cannot appear
    in this module, because every use of it makes the fallback below it
    dead code."""
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parents[2] / "gcp" / "trade_logger.py").read_text()
    bad = [l for l in src.splitlines()
           if "query_to_dataframe" in l and "query_to_dataframe_strict" not in l
           and not l.lstrip().startswith("#")]
    assert bad == [], (
        "these lines read through the swallowing helper, so their except "
        "clause and Parquet fallback are unreachable: %s" % bad)
