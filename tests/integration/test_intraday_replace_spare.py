"""--replace-months on a real Postgres: the swap that spares listed keys.

The hermetic cases in tests/gcp/test_intraday_replace_months.py read the SQL
text off a mocked engine. These run it: the row lock, the DELETE that leaves
the spared keys alone, the derived-table clear over the whole window, and the
row digest, against the real `market_data_intraday` DDL.

Spec: docs/superpowers/specs/2026-11-14-feat-data-001-replace-held-session-window.md
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import gcp.database as db

UTC = timezone.utc
TICKER = "ZZSPARE"          # no production ticker; lands in the DEFAULT partition
OLD = datetime(2020, 1, 1, tzinfo=UTC)
ALL = "ticker, interval, ts, open, high, low, close, volume, data_source, inserted_at"


@pytest.fixture
def own_rows(db_engine):
    """This file's rows only: nothing else in the database is touched."""
    import sqlalchemy

    def wipe():
        with db_engine.begin() as conn:
            for t in ("market_data_intraday", "intraday_flow_15m"):
                conn.execute(sqlalchemy.text(f"DELETE FROM {t} WHERE ticker = :t"), {"t": TICKER})
    wipe()
    yield
    wipe()


def _stored(ts: datetime, n: int) -> dict:
    return {"ticker": TICKER, "interval": "1min", "ts": ts, "open": 100.0 + n, "high": 100.5 + n,
            "low": 99.5 + n, "close": 100.25 + n, "volume": 1000 + n,
            "data_source": "alphavantage", "inserted_at": OLD}


def _frame(ts: list[datetime], base: float) -> pd.DataFrame:
    return pd.DataFrame({"ticker": TICKER, "interval": "1min", "ts": pd.DatetimeIndex(ts),
                         "open": base, "high": base + 0.5, "low": base - 0.5, "close": base + 0.25,
                         "volume": 7, "data_source": "alphavantage"})


def _window(run_sql, start: datetime, end: datetime) -> pd.DataFrame:
    return run_sql(f"SELECT {ALL} FROM market_data_intraday WHERE ticker = :t AND ts >= :s AND ts < :e "
                   "ORDER BY ts", {"t": TICKER, "s": start, "e": end})


def test_two_spared_keys_survive_a_swap_of_ten_rows(own_rows, seed, run_sql):
    """Design 4, done_when[7]: ten rows in the window, two of them spared. The
    two stay equal in every column, inserted_at included; the other eight go;
    the frame comes in; the derived table is cleared over the whole window."""
    start = datetime(2018, 3, 1, 2, 0, tzinfo=UTC)
    end = start + timedelta(minutes=10)
    keys = [start + timedelta(minutes=n) for n in range(10)]
    seed("market_data_intraday", [_stored(k, n) for n, k in enumerate(keys)])
    seed("intraday_flow_15m", [{"ticker": TICKER, "ts": start, "n_min": 10}])
    spare = [keys[4], keys[7]]
    before = _window(run_sql, start, end)
    assert len(before) == 10
    spared_before = before[before["ts"].isin(spare)].reset_index(drop=True)

    cleared: dict = {}
    out = db.replace_rows_in_window(
        _frame(keys[:3], 500.0), "market_data_intraday", {"ticker": TICKER, "interval": "1min"},
        "ts", start, end, max_delete_ratio=3.0, verify=lambda conn: None,
        clear_tables=("intraday_flow_15m",), cleared=cleared, spare_ts=spare)

    assert out == (8, 3)
    after = _window(run_sql, start, end)
    assert list(after["ts"]) == [keys[0], keys[1], keys[2], keys[4], keys[7]]
    pd.testing.assert_frame_equal(after[after["ts"].isin(spare)].reset_index(drop=True), spared_before)
    written = after[~after["ts"].isin(spare)]
    assert list(written["open"]) == [500.0, 500.0, 500.0] and list(written["volume"]) == [7, 7, 7]
    assert (written["inserted_at"] > pd.Timestamp("2026-01-01", tz="UTC")).all()
    assert cleared == {"intraday_flow_15m": 1}
    assert run_sql("SELECT count(*) AS n FROM intraday_flow_15m WHERE ticker = :t",
                   {"t": TICKER})["n"].iloc[0] == 0
