"""--replace-months on a real Postgres: the swap that spares listed keys.

The hermetic cases in tests/gcp/test_intraday_replace_months.py read the SQL
text off a mocked engine, and run replace_month over an in-memory table. These
run the statements: the row lock, the DELETE that leaves the spared keys
alone, the derived-table clear over the whole window, the snapshot and key
reads and the row digest, against the real `market_data_intraday` DDL. In the
replace_month cases only the vendor request is stubbed.

Spec: docs/superpowers/specs/2026-11-14-feat-data-001-replace-held-session-window.md
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import gcp.database as db
import gcp.fetchers.fetch_alphavantage_intraday as fai
from tests.gcp.test_intraday_replace_months import (
    FEB_LATE, OTHER_STRIP_KEYS, _bars, _february, _feb_late_and_march, _iwm_session,
    _iwm_stored, _true_rows,
)

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


# -- replace_month end to end: only the vendor request is stubbed ------------

RUN_STARTED = pd.Timestamp("2026-01-01", tz="UTC")    # any inserted_at after it is this test's


def _seed(rows: pd.DataFrame) -> None:
    """Stored rows (ts and the five fields) as an earlier writer left them."""
    db.upsert_dataframe(
        rows.assign(ticker=TICKER, interval="1min", data_source="alphavantage", inserted_at=OLD),
        "market_data_intraday", conflict_cols=["ticker", "interval", "ts"], chunksize=5000)


def _vendor(frame: pd.DataFrame, during=None):
    """A fetch_month that answers with *frame*, after calling *during*."""
    def fetch(symbol, year, month, api_key):
        if during is not None:
            during()
        return frame.assign(ticker=symbol), fai.FETCH_OK
    return fetch


def _rows_at(run_sql, keys) -> pd.DataFrame:
    out = run_sql(f"SELECT {ALL} FROM market_data_intraday WHERE ticker = :t ORDER BY ts", {"t": TICKER})
    return out[out["ts"].isin(list(keys))].reset_index(drop=True)


def _older(rows: pd.DataFrame) -> pd.DataFrame:
    """The same keys with other values: what an earlier fetch stored."""
    return rows.assign(close=rows["close"] + 1.0, volume=rows["volume"] + 5)


def test_a_month_and_its_tail_are_replaced_on_postgres(own_rows, seed, run_sql, monkeypatch):
    """Design 5 on the real statements: the window swap, the key read, and the
    second swap that writes the three late bars and spares the rest of the
    strip. Run twice: the second run converges on the same rows."""
    stored, feb = _february()
    _seed(_older(stored))
    feb_start, feb_end = fai.month_replace_window(2018, 2)
    seed("intraday_flow_15m", [{"ticker": TICKER, "ts": k, "n_min": 15} for k in (
        datetime(2018, 2, 28, 14, 30, tzinfo=UTC),      # inside February's window
        datetime(2018, 3, 1, 3, 0, tzinfo=UTC),         # inside the tail swap's range
        datetime(2018, 3, 1, 4, 45, tzinfo=UTC))])      # past the last tail key: not this swap's
    spared_before = _rows_at(run_sql, OTHER_STRIP_KEYS)
    assert len(spared_before) == 2
    monkeypatch.setattr(fai, "fetch_month", _vendor(feb))

    r = fai.replace_month(TICKER, 2018, 2, "k", commit=True)

    assert r["status"] == fai.REPLACE_OK, r
    assert (r["tail"], r["deleted"], r["inserted"]) == (3, 964, 964)
    assert r["derived_cleared"] == {"intraday_flow_15m": 2}
    pd.testing.assert_frame_equal(_rows_at(run_sql, OTHER_STRIP_KEYS), spared_before)
    written = _window(run_sql, feb_start, datetime(2018, 3, 1, 5, 0, tzinfo=UTC))
    written = written[~written["ts"].isin(OTHER_STRIP_KEYS)].reset_index(drop=True)
    want = _true_rows(feb).sort_values("ts").reset_index(drop=True)
    assert list(written["ts"]) == list(want["ts"]) and len(written) == 964
    for f in ("open", "high", "low", "close", "volume"):
        assert list(written[f]) == list(want[f]), f
    assert (written["inserted_at"] > RUN_STARTED).all()
    left = run_sql("SELECT ts FROM intraday_flow_15m WHERE ticker = :t", {"t": TICKER})
    assert list(left["ts"]) == [pd.Timestamp("2018-03-01 04:45", tz="UTC")]

    again = fai.replace_month(TICKER, 2018, 2, "k", commit=True)
    assert (again["status"], again["tail"], again["deleted"], again["inserted"]) == (fai.REPLACE_OK, 3, 964, 964)
    pd.testing.assert_frame_equal(_rows_at(run_sql, OTHER_STRIP_KEYS), spared_before)
    after = _window(run_sql, feb_start, datetime(2018, 3, 1, 5, 0, tzinfo=UTC))
    assert len(after) == 966
    assert list(after[~after["ts"].isin(OTHER_STRIP_KEYS)]["close"]) == list(want["close"])


def test_a_tail_key_rewritten_during_the_run_keeps_the_newer_row_on_postgres(own_rows, run_sql,
                                                                                monkeypatch, db_engine):
    """done_when[4] on the real digest: while the vendor answers, another
    writer updates the row at 02:04Z in place, new values and a new
    inserted_at, no key added or removed. The second swap rolls back."""
    import sqlalchemy
    stored, feb = _february()
    _seed(_older(stored))
    keys_before = list(run_sql("SELECT ts FROM market_data_intraday WHERE ticker = :t ORDER BY ts",
                               {"t": TICKER})["ts"])

    def nightly_upsert():
        with db_engine.begin() as conn:
            n = conn.execute(sqlalchemy.text(
                "UPDATE market_data_intraday SET open = 1, high = 2, low = 0.5, close = 1.5, "
                "volume = 4242, inserted_at = NOW() WHERE ticker = :t AND ts = :k"),
                {"t": TICKER, "k": FEB_LATE[0].to_pydatetime()}).rowcount
        assert n == 1
    monkeypatch.setattr(fai, "fetch_month", _vendor(feb, during=nightly_upsert))

    r = fai.replace_month(TICKER, 2018, 2, "k", commit=True)

    assert r["status"] == fai.REPLACE_TAIL_NOT_WRITTEN, r
    assert "tail strip changed" in r["detail"]
    assert (r["deleted"], r["inserted"]) == (961, 961)            # the window's swap committed
    late = _rows_at(run_sql, FEB_LATE)
    newer = late.iloc[0]
    assert (newer["open"], newer["high"], newer["low"], newer["close"], newer["volume"]) == (1, 2, 0.5, 1.5, 4242)
    assert newer["inserted_at"] > RUN_STARTED
    assert (late["inserted_at"].iloc[1:] == pd.Timestamp(OLD)).all()   # the tail swap wrote nothing
    assert list(run_sql("SELECT ts FROM market_data_intraday WHERE ticker = :t ORDER BY ts",
                        {"t": TICKER})["ts"]) == keys_before


def test_a_window_row_rewritten_during_the_run_rolls_the_month_back_on_postgres(own_rows, run_sql,
                                                                                  monkeypatch, db_engine):
    """The guard this change keeps (#1185): a same-count rewrite inside the
    window while the vendor answers is seen by the digest under the lock, and
    nothing is deleted."""
    import sqlalchemy
    stored, feb = _february()
    _seed(_older(stored))
    key = datetime(2018, 2, 28, 14, 30, tzinfo=UTC)

    def nightly_upsert():
        with db_engine.begin() as conn:
            conn.execute(sqlalchemy.text(
                "UPDATE market_data_intraday SET close = 999, inserted_at = NOW() "
                "WHERE ticker = :t AND ts = :k"), {"t": TICKER, "k": key})
    monkeypatch.setattr(fai, "fetch_month", _vendor(feb, during=nightly_upsert))

    r = fai.replace_month(TICKER, 2018, 2, "k", commit=True)

    assert r["status"] == fai.REPLACE_CHANGED, r
    assert (r["deleted"], r["inserted"]) == (0, 0)
    rows = run_sql(f"SELECT {ALL} FROM market_data_intraday WHERE ticker = :t", {"t": TICKER})
    assert len(rows) == 966
    assert rows[rows["ts"] == pd.Timestamp(key)]["close"].iloc[0] == 999
    assert (rows[rows["ts"] != pd.Timestamp(key)]["inserted_at"] == pd.Timestamp(OLD)).all()


def test_march_spares_februarys_late_bars_on_postgres(own_rows, run_sql, monkeypatch):
    """Design 4 through replace_month: March's swap leaves February's late
    bars equal in every column and replaces March's own session."""
    stored, march = _feb_late_and_march()
    _seed(_older(stored))
    late_before = _rows_at(run_sql, FEB_LATE)
    monkeypatch.setattr(fai, "fetch_month", _vendor(march))

    r = fai.replace_month(TICKER, 2018, 3, "k", commit=True)

    assert r["status"] == fai.REPLACE_OK, r
    assert (r["carry_in"], r["tail"], r["deleted"], r["inserted"]) == (3, 0, 961, 961)
    pd.testing.assert_frame_equal(_rows_at(run_sql, FEB_LATE), late_before)
    rest = run_sql(f"SELECT {ALL} FROM market_data_intraday WHERE ticker = :t ORDER BY ts", {"t": TICKER})
    rest = rest[~rest["ts"].isin(FEB_LATE)]
    assert len(rest) == 961 and (rest["inserted_at"] > RUN_STARTED).all()


def test_label_copies_are_told_apart_after_a_round_trip_through_postgres(own_rows, run_sql, monkeypatch):
    """Design 3 on stored values: the five fields come back from DOUBLE
    PRECISION and BIGINT columns equal to the vendor's, so the 34 copies are
    found, and the replaced month holds the refetch and no row at a UTC clock
    time before 08:00 (the spec's Close-out check for IWM 2026-04)."""
    v = _iwm_session()
    _seed(_iwm_stored(v))
    monkeypatch.setattr(fai, "fetch_month", _vendor(v))

    dry = fai.replace_month(TICKER, 2026, 4, "k", commit=False)
    assert (dry["status"], dry["label_copies"], dry["label_dropped"], dry["rows"]) == (fai.REPLACE_DRY, 34, 206, 1082)
    assert len(run_sql("SELECT ts FROM market_data_intraday WHERE ticker = :t", {"t": TICKER})) == 1082

    r = fai.replace_month(TICKER, 2026, 4, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK, r
    assert (r["label_copies"], r["label_dropped"], r["deleted"], r["inserted"]) == (34, 206, 1082, 842)
    rows = run_sql(f"SELECT {ALL} FROM market_data_intraday WHERE ticker = :t ORDER BY ts", {"t": TICKER})
    assert list(rows["ts"]) == sorted(_true_rows(v)["ts"])
    assert rows["ts"].dt.hour.min() >= 8
