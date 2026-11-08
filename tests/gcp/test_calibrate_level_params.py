"""FEAT-STRAT-001 per-ticker params, done_when 8: the calibration job's I/O
shape (gcp/calibrate_level_params.py).

The tables are level_param_policy and ticker_level_params created in SQLite
from gcp/schema.sql (tests.lib.level_params_fixtures.ParamsDb); rows are
written with the job's own ON CONFLICT statement. Daily bars are the committed
2026-11-06 fixture with ATR(14) and ATR(5); one-minute bars are synthetic,
stored as true UTC (dates after lib.eastern_time.TRUE_UTC_FROM).

* N tickers cost exactly N daily reads, N one-minute reads and N write
  batches (plus one policy read).
* A rerun for the same night converges to the same rows.
* One ticker's failed read is logged and skipped, and the run exits
  non-zero.
* History mode writes one version per session, each from bars strictly
  before it, equal to a nightly run for that session.
* The module is not wired into gcp/deploy.sh (Design 9).

On origin/main and the #1753 head the module does not exist.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gcp import calibrate_level_params as job
from lib.indicators import calculate_atr
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import ParamsDb

ROOT = Path(__file__).resolve().parents[2]
TICKERS = ["SPY", "QQQ", "IWM"]
EFF = date(2026, 11, 6)


def _daily(ticker):
    d = fx.daily(ticker, through=date(2026, 11, 5))
    out = pd.DataFrame({
        "date": d.index.date, "open": d["Open"].values, "high": d["High"].values,
        "low": d["Low"].values, "close": d["Close"].values,
        "atr_14": calculate_atr(d["High"], d["Low"], d["Close"], 14).values,
        "atr_5": calculate_atr(d["High"], d["Low"], d["Close"], 5).values,
    })
    return out


def _minutes(ticker):
    """Premarket and RTH one-minute bars for every session from 2026-09-28,
    from each day's OHLC, as stored (true UTC ts)."""
    d = fx.daily(ticker, through=date(2026, 11, 5))
    d = d[d.index >= pd.Timestamp("2026-09-28")]
    frames = []
    for s, r in d.iterrows():
        rth = np.concatenate([np.linspace(r.Open, r.High, 130), np.linspace(r.High, r.Low, 130),
                              np.linspace(r.Low, r.Close, 130)])
        et = pd.date_range(f"{s.date()} 09:30", periods=390, freq="1min")
        pm = pd.date_range(f"{s.date()} 07:00", periods=150, freq="1min")
        ts = et.append(pm).tz_localize("America/New_York").tz_convert("UTC")
        px = np.concatenate([rth, np.full(150, r.Open)])
        frames.append(pd.DataFrame({"ts": ts, "open": px, "high": px + 0.02, "low": px - 0.02,
                                    "close": px, "volume": 100}))
    return pd.concat(frames, ignore_index=True)


class FakeDb:
    """Routes the job's SQL: policy and on_demand reads to the ParamsDb,
    daily and one-minute reads to the fixtures; counts every read and
    write batch."""

    def __init__(self, fail_daily=()):
        self.pdb = ParamsDb()
        self.reads = {"policy": 0, "daily": [], "minutes": [], "on_demand": 0}
        self.batches = []
        self.fail_daily = set(fail_daily)
        self.daily = {t: _daily(t) for t in TICKERS}
        self.minutes = {t: _minutes(t) for t in TICKERS}

    def query(self, sql, params=None):
        params = params or {}
        if sql == job.POLICY_SQL:
            self.reads["policy"] += 1
            return self.pdb.query(sql, params)
        if sql == job.ON_DEMAND_SQL:
            self.reads["on_demand"] += 1
            return self.pdb.query(sql, params)
        if sql == job.DAILY_SQL:
            t = params["ticker"]
            self.reads["daily"].append(t)
            if t in self.fail_daily:
                raise RuntimeError("connection reset")
            df = self.daily[t]
            keep = (pd.to_datetime(df["date"]) >= pd.Timestamp(params["start"])) & \
                   (pd.to_datetime(df["date"]) < pd.Timestamp(params["before"]))
            return df[keep].reset_index(drop=True)
        if sql == job.MINUTES_SQL:
            t = params["ticker"]
            self.reads["minutes"].append(t)
            df = self.minutes[t]
            # The job passes aware UTC bounds.
            keep = (df["ts"] >= pd.Timestamp(params["start"])) & (df["ts"] < pd.Timestamp(params["end"]))
            return df[keep].reset_index(drop=True)
        raise AssertionError(f"unexpected SQL {sql[:60]}")

    def write(self, rows):
        self.batches.append(len(rows))
        self.pdb.conn.executemany(job.UPSERT_SQL, rows)
        self.pdb.conn.commit()
        return len(rows)

    def rows(self, cols="ticker, param_key, value, status, atr_basis, method_id, sample_n, "
                        "input_from, input_to, effective_from, source"):
        return pd.read_sql_query(f"SELECT {cols} FROM ticker_level_params "
                                 "ORDER BY ticker, param_key, effective_from", self.pdb.conn)


def _run(db, tickers=TICKERS, dates=(EFF,), source="nightly"):
    policy = job.read_policy(db.query, max(dates))
    return job.run(list(tickers), list(dates), query=db.query, write=db.write,
                   policy=policy, source=source)


def test_n_tickers_cost_n_reads_and_n_write_batches():
    db = FakeDb()
    res = _run(db)
    assert res.exit_code == 0 and res.succeeded == TICKERS
    assert db.reads["policy"] == 1
    assert db.reads["daily"] == TICKERS and db.reads["minutes"] == TICKERS
    assert len(db.batches) == 3
    rows = db.rows()
    assert len(rows) == 3 * 23 and set(rows["effective_from"]) == {"2026-11-06"}
    assert set(rows["source"]) == {"nightly"}
    # Every row carries its method, sample, input range and run id.
    full = db.rows("run_id, method_id, sample_n, calibrated_at, value, status")
    assert full["run_id"].nunique() == 1 and full["method_id"].notna().all()
    assert full["sample_n"].notna().all() and full["calibrated_at"].notna().all()
    assert ((full["status"] == "ok") == full["value"].notna()).all()
    # The daily trigger windows have the history to calibrate.
    spy = rows[(rows["ticker"] == "SPY") & (rows["param_key"] == "trigger_window_long_atr")].iloc[0]
    assert spy["status"] == "ok" and spy["input_to"] == "2026-11-05"


def test_a_rerun_for_the_same_night_converges():
    db = FakeDb()
    _run(db)
    first = db.rows()
    res = _run(db)
    second = db.rows()
    pd.testing.assert_frame_equal(first, second)
    runs = pd.read_sql_query("SELECT DISTINCT run_id FROM ticker_level_params", db.pdb.conn)
    assert list(runs["run_id"]) == [res.run_id]


def test_one_failed_read_skips_that_ticker_and_the_run_exits_non_zero(caplog):
    db = FakeDb(fail_daily={"QQQ"})
    with caplog.at_level(logging.ERROR):
        res = _run(db)
    assert res.failed == ["QQQ"] and res.succeeded == ["SPY", "IWM"]
    assert res.exit_code == 1
    assert "QQQ failed, skipped" in caplog.text
    assert sorted(db.rows()["ticker"].unique()) == ["IWM", "SPY"]
    assert len(db.batches) == 2


def test_history_mode_writes_each_session_from_bars_before_it():
    sessions = [date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]
    hist = FakeDb()
    res = _run(hist, tickers=["SPY"], dates=sessions, source="history")
    assert res.exit_code == 0 and len(hist.batches) == 1
    assert hist.reads["daily"] == ["SPY"] and hist.reads["minutes"] == ["SPY"]
    rows = hist.rows()
    assert sorted(rows["effective_from"].unique()) == [d.isoformat() for d in sessions]
    assert (rows["input_to"].dropna() < rows.loc[rows["input_to"].notna(), "effective_from"]).all()
    windows = rows[rows["param_key"] == "trigger_window_long_atr"].set_index("effective_from")
    assert windows.loc["2026-11-04", "input_to"] == "2026-11-03"
    # Each version equals a nightly run effective that session.
    for d in (sessions[0], sessions[-1]):
        night = FakeDb()
        _run(night, tickers=["SPY"], dates=[d])
        a = rows[rows["effective_from"] == d.isoformat()].drop(columns="source").reset_index(drop=True)
        b = night.rows().drop(columns="source").reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)


def test_main_exits_non_zero_when_a_ticker_fails(monkeypatch):
    import gcp.database as database

    db = FakeDb(fail_daily={"IWM"})
    recorded = []
    monkeypatch.setattr(database, "query_to_dataframe_strict", db.query)
    monkeypatch.setattr(database, "record_job_run", lambda *a, **k: recorded.append((a, k)) or True)
    monkeypatch.setattr(job, "_engine_writer", lambda: db.write)
    assert job.main(["--tickers", "SPY,IWM", "--effective-from", "2026-11-06"]) == 1
    assert recorded and recorded[0][0][2] == "failed" and recorded[0][1]["items_failed"] == 1
    assert job.main(["--tickers", "SPY", "--effective-from", "2026-11-06"]) == 0


def test_main_raises_when_the_policy_is_unreadable(monkeypatch):
    import gcp.database as database
    from lib.strat_levels import LevelParamsUnavailable

    db = FakeDb()
    db.pdb.drop("level_param_policy")
    monkeypatch.setattr(database, "query_to_dataframe_strict", db.query)
    with pytest.raises(LevelParamsUnavailable):
        job.main(["--tickers", "SPY", "--effective-from", "2026-11-06"])


def test_default_universe_is_the_policy_sources(monkeypatch):
    db = FakeDb()
    db.pdb.write("ZZZ", {"trigger_window_long_atr": 2.0}, effective_from=EFF, source="on_demand")
    policy = job.read_policy(db.query, EFF)
    got = job.calibration_universe(policy, db.query, watchlist_fn=lambda: ["AAPL", "spy"])
    assert got[:3] == ["IWM", "SPY", "QQQ"] and got[-2:] == ["AAPL", "ZZZ"]


def test_not_in_deploy_sh():
    deploy = (ROOT / "gcp" / "deploy.sh").read_text()
    assert "calibrate_level_params" not in deploy and "calibrate-level-params" not in deploy
