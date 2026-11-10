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
  before it and under the policy in force on it, equal to a nightly run for
  that session; it writes in chunks of sessions, so a failure keeps the
  chunks written and a rerun converges.
* A basis switch follows Design 4's order: the new-basis history run writes
  beside the old rows, and after the policy row takes effect on D a session
  before D still reads the old values.
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
    rows = job.read_policy_rows(db.query, max(dates))
    return job.run(list(tickers), list(dates), query=db.query, write=db.write,
                   policy_rows=rows, source=source)


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


# ── review findings 1 and 2: per-session policy, chunks, basis switch ──

HIST = ["2026-11-03", "2026-11-06"]
SESSIONS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
KEEP = ("ticker, param_key, value, status, atr_basis, method_id, policy_effective_from, "
        "sample_n, input_from, input_to, effective_from")


def _main(monkeypatch, db, *args):
    import gcp.database as database

    monkeypatch.setattr(database, "query_to_dataframe_strict", db.query)
    monkeypatch.setattr(database, "record_job_run", lambda *a, **k: True)
    monkeypatch.setattr(job, "_engine_writer", lambda: db.write)
    return job.main(["--tickers", "SPY", *args])


def _add_policy(db, key, effective_from, **fields):
    """A later policy row for `key`: the latest row's fields with `fields`
    changed, effective `effective_from`."""
    cols = ("method_id", "statistic_q", "lookback_sessions", "min_sample", "extra")
    latest = db.pdb.conn.execute(
        f"SELECT {', '.join(cols)} FROM level_param_policy WHERE param_key = ? "
        "ORDER BY effective_from DESC LIMIT 1", (key,)).fetchone()
    row = {**dict(zip(cols, latest)), **fields}
    db.pdb.conn.execute(
        f"INSERT INTO level_param_policy ({', '.join(cols)}, param_key, effective_from) "
        "VALUES (?,?,?,?,?,?,?)", (*[row[c] for c in cols], key, effective_from))
    db.pdb.conn.commit()


def _on(rows, day):
    return rows[rows["effective_from"] == day].reset_index(drop=True)


def test_history_mode_uses_the_policy_in_force_on_each_session(monkeypatch):
    """Two policy rows for trigger_window_long_atr, the second (coverage
    0.95) effective 2026-11-05. A history rerun over 11-03..11-06 leaves the
    11-03 and 11-04 rows as the first run wrote them under the old row, and
    writes 11-05 and 11-06 under the new row, each equal to a nightly run
    for that session."""
    db = FakeDb()
    assert _main(monkeypatch, db, "--history", *HIST) == 0
    before = db.rows(KEEP)
    _add_policy(db, "trigger_window_long_atr", "2026-11-05", statistic_q=0.95)
    assert _main(monkeypatch, db, "--history", *HIST) == 0
    after = db.rows(KEEP)
    for day in SESSIONS[:2]:
        pd.testing.assert_frame_equal(_on(after, day), _on(before, day))
    key = after["param_key"] == "trigger_window_long_atr"
    changed = after[key].set_index("effective_from")
    old = before[before["param_key"] == "trigger_window_long_atr"].set_index("effective_from")
    for day in SESSIONS[2:]:
        assert changed.loc[day, "policy_effective_from"] == "2026-11-05"
        assert changed.loc[day, "value"] < old.loc[day, "value"]
        # Every other key is unchanged on those sessions.
        pd.testing.assert_frame_equal(_on(after[~key], day), _on(before[~key], day))
    night = FakeDb()
    _add_policy(night, "trigger_window_long_atr", "2026-11-05", statistic_q=0.95)
    assert _main(monkeypatch, night, "--effective-from", "2026-11-06") == 0
    pd.testing.assert_frame_equal(_on(after, "2026-11-06"), night.rows(KEEP))


class _FailingWrites(FakeDb):
    def __init__(self, fail_batch):
        super().__init__()
        self.fail_batch = fail_batch

    def write(self, rows):
        if len(self.batches) + 1 == self.fail_batch:
            self.batches.append(None)
            raise RuntimeError("connection reset")
        return super().write(rows)


def test_history_mode_writes_in_chunks_and_a_rerun_converges(monkeypatch):
    """Two sessions per write batch; the second batch fails. The first
    two sessions' rows stay, the run exits non-zero, and a rerun writes the
    rest and leaves the first two as they were."""
    db = _FailingWrites(fail_batch=2)
    assert _main(monkeypatch, db, "--history", *HIST, "--chunk-sessions", "2") == 1
    partial = db.rows(KEEP)
    assert sorted(partial["effective_from"].unique()) == SESSIONS[:2]
    assert len(db.batches) == 2 and db.batches[0] == 2 * 23
    db.fail_batch = 0
    assert _main(monkeypatch, db, "--history", *HIST, "--chunk-sessions", "2") == 0
    full = db.rows(KEEP)
    assert sorted(full["effective_from"].unique()) == SESSIONS
    for day in SESSIONS[:2]:
        pd.testing.assert_frame_equal(_on(full, day), _on(partial, day))
    # Chunked rows equal one batch's.
    one = FakeDb()
    assert _main(monkeypatch, one, "--history", *HIST) == 0
    assert len(one.batches) == 1
    pd.testing.assert_frame_equal(full, one.rows(KEEP))


def test_basis_switch_follows_the_transition_order(monkeypatch):
    """Design 4: history in the new basis first (--atr-basis atr_5), then
    the policy row effective D = 2026-11-05. The preparation run overwrites
    no atr_14 row; a session before D reads the same atr_14 values before
    the preparation run, after it and after D; a session on or after D
    reads the atr_5 rows."""
    db = FakeDb()
    assert _main(monkeypatch, db, "--history", *HIST) == 0
    old = db.rows(KEEP)
    early, late = date(2026, 11, 4), date(2026, 11, 6)

    def values(day):
        lp = db.pdb.load(["SPY"], day)["SPY"]
        return lp.atr_basis, {k: (p.status, p.value) for k, p in lp.params.items()}

    first = values(early)
    assert first[0] == "atr_14"
    assert _main(monkeypatch, db, "--history", *HIST, "--atr-basis", "atr_5") == 0
    prepared = db.rows(KEEP)
    pd.testing.assert_frame_equal(prepared[prepared["atr_basis"] == "atr_14"].reset_index(drop=True),
                                  old)
    assert sorted(prepared.loc[prepared["atr_basis"] == "atr_5", "effective_from"].unique()) == SESSIONS
    assert values(early) == first and values(late)[0] == "atr_14"
    db.pdb.set_policy("atr_basis", effective_from=date(2026, 11, 5), extra='{"column": "atr_5"}')
    assert _main(monkeypatch, db, "--history", *HIST) == 0
    switched = db.rows(KEEP)
    pd.testing.assert_frame_equal(switched[switched["atr_basis"] == "atr_14"].reset_index(drop=True),
                                  old)
    assert values(early) == first
    basis, late_values = values(late)
    assert basis == "atr_5" and all(st != "params_basis_mismatch" for st, _ in late_values.values())
    atr5 = switched[(switched["atr_basis"] == "atr_5") & (switched["effective_from"] == "2026-11-06")]
    assert {k: (st, None if pd.isna(v) else v)
            for k, st, v in zip(atr5["param_key"], atr5["status"], atr5["value"])} == late_values
    assert late_values["trigger_window_long_atr"][0] == "ok"


# ── Codex P2 on e4bb463e: the watchlist is read strictly ───────────────


def _watchlist_query(db, tickers=None, fail=False):
    def query(sql, params=None):
        if sql == job.WATCHLIST_SQL:
            assert params == {"user_id": "default"}
            if fail:
                raise RuntimeError("connection reset")
            return pd.DataFrame({"ticker": list(tickers or [])})
        return db.query(sql, params)
    return query


def test_a_failed_watchlist_read_fails_the_universe():
    db = FakeDb()
    policy = job.read_policy(db.query, EFF)
    with pytest.raises(RuntimeError, match="connection reset"):
        job.calibration_universe(policy, _watchlist_query(db, fail=True))


def test_an_empty_watchlist_is_a_valid_universe_member():
    db = FakeDb()
    policy = job.read_policy(db.query, EFF)
    empty = job.calibration_universe(policy, _watchlist_query(db, []))
    got = job.calibration_universe(policy, _watchlist_query(db, ["AAPL", "spy"]))
    assert "AAPL" not in empty and got[-1] == "AAPL" and got[:len(empty)] == empty


def test_the_one_minute_fetch_universe_reads_the_watchlist_strictly(monkeypatch):
    import gcp.database as database

    def broken(sql, params=None):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(database, "query_to_dataframe_strict", broken)
    with pytest.raises(RuntimeError, match="connection reset"):
        job.brief_insight_watchlist_tickers()
    monkeypatch.setattr(database, "query_to_dataframe_strict",
                        lambda sql, params=None: pd.DataFrame({"ticker": ["NVDA"]}))
    assert job.brief_insight_watchlist_tickers()[-1] == "NVDA"
