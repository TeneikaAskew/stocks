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
