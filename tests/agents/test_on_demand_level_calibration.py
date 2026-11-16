"""FEAT-STRAT-001 per-ticker params, review finding 3: on-demand calibration
(spec Design 3).

When an insight run's ticker has no ticker_level_params row, the run
calibrates it (lib.level_calibration.calibrate_ticker) before planning and
writes the rows with source on_demand, through the calibration job's own
reads and ON CONFLICT write. The tables are SQLite from gcp/schema.sql
(tests.lib.level_params_fixtures.ParamsDb); the daily bars are the committed
2026-11-06 fixture.

* A ticker with enough daily bars gets on_demand rows effective on the
  session, ok trigger windows in its level_basis, and from then on the
  job's on_demand universe source lists it.
* A ticker with 100 daily bars and no one-minute bars gets rows that say
  insufficient_history, and both sides are orb_only with reason
  params_insufficient_history, not params_unavailable.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from gcp import calibrate_level_params as job
from lib.agents import summarizers
from lib.strat_levels import POLICY_SEEDED_KEYS, SessionLevels
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import LEGACY_1753_VALUES, ParamsDb

# One row per per-ticker key: the calibrated keys and the policy_seed keys
# (target_min_spacing_atr, gap_fill_flag_atr), which carry the policy's seed.
TICKER_KEYS = len(LEGACY_1753_VALUES)

SESSION = date(2026, 11, 6)
NEW = "NEWT"


def _job_daily(frame):
    d = frame[frame["Close"].notna()]
    return pd.DataFrame({"date": d.index.date, "open": d["Open"].values, "high": d["High"].values,
                         "low": d["Low"].values, "close": d["Close"].values,
                         "atr_14": d["ATR14"].values, "atr_5": d["ATR5"].values})


@pytest.fixture
def world(monkeypatch):
    """The ticker NEWT has the QQQ bars and no parameter rows. `bars`
    keeps that many daily bars before the session."""
    import gcp.database as database

    pdb = ParamsDb()
    state = {"frame": fx.loader_frame("QQQ"), "writes": []}

    def strict(sql, params=None):
        params = params or {}
        if sql == job.DAILY_SQL:
            assert params["ticker"] == NEW
            d = _job_daily(state["frame"])
            keep = (pd.to_datetime(d["date"]) >= pd.Timestamp(params["start"])) & \
                   (pd.to_datetime(d["date"]) < pd.Timestamp(params["before"]))
            return d[keep].reset_index(drop=True)
        if sql == job.MINUTES_SQL:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return pdb.query(sql, params)

    def write(rows):
        state["writes"].append(len(rows))
        pdb.conn.executemany(job.UPSERT_SQL, rows)
        pdb.conn.commit()
        return len(rows)

    class _Loader:
        def load_daily(self, *a, **k):
            return state["frame"].copy()

    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    monkeypatch.setattr(job, "_engine_writer", lambda: write)
    monkeypatch.setattr(summarizers, "_query", lambda sql, params=None: pd.DataFrame())
    state.update(pdb=pdb, loader=_Loader())
    return state


def _rows(pdb):
    return pd.read_sql_query("SELECT param_key, status, value, source, effective_from, input_to "
                             "FROM ticker_level_params WHERE ticker = 'NEWT'", pdb.conn)


def test_a_ticker_without_rows_is_calibrated_on_demand(world):
    out = summarizers.summarize_session_levels(NEW, as_of=SESSION, loader=world["loader"])
    rows = _rows(world["pdb"])
    assert len(world["writes"]) == 1 and len(rows) == TICKER_KEYS
    assert set(rows["source"]) == {"on_demand"} and set(rows["effective_from"]) == {"2026-11-06"}
    assert (rows["input_to"].dropna() < "2026-11-06").all()
    windows = rows.set_index("param_key").loc[["trigger_window_long_atr", "trigger_window_short_atr"]]
    assert (windows["status"] == "ok").all()
    params = out["level_basis"]["params"]
    for key in ("trigger_window_long_atr", "trigger_window_short_atr"):
        assert params[key]["status"] == "ok" and params[key]["source"] == "on_demand"
    sl = SessionLevels.from_basis(out["level_basis"])
    assert sl.long.reason != "params_unavailable" and sl.short.reason != "params_unavailable"
    # No one-minute bars: those keys say so, typed.
    assert params["pm_spike_atr"]["status"] == "insufficient_history"
    # The job's on_demand universe source now lists the ticker.
    policy = job.read_policy(world["pdb"].query, SESSION)
    assert NEW in job.calibration_universe(policy, world["pdb"].query, watchlist_fn=lambda: [])
    # A second run finds the rows and does not calibrate again.
    summarizers.summarize_session_levels(NEW, as_of=SESSION, loader=world["loader"])
    assert len(world["writes"]) == 1


def test_a_ticker_with_100_bars_gets_insufficient_history(world):
    frame = world["frame"]
    world["frame"] = frame.iloc[-101:]  # 100 completed bars and the session's own row
    out = summarizers.summarize_session_levels(NEW, as_of=SESSION, loader=world["loader"])
    rows = _rows(world["pdb"]).set_index("param_key")
    assert len(rows) == TICKER_KEYS and set(rows["source"]) == {"on_demand"}
    assert rows.loc["trigger_window_long_atr", "status"] == "insufficient_history"
    assert rows.loc["trigger_window_short_atr", "status"] == "insufficient_history"
    calibrated = rows.drop(index=list(POLICY_SEEDED_KEYS))
    assert (calibrated["status"] != "ok").all() and calibrated["value"].isna().all()
    # A policy seed needs no bars: those keys are ok at the policy's seed.
    seeded = rows.loc[list(POLICY_SEEDED_KEYS)]
    assert (seeded["status"] == "ok").all() and seeded["value"].notna().all()
    sl = SessionLevels.from_basis(out["level_basis"])
    for side in (sl.long, sl.short):
        assert side.regime == "orb_only" and side.reason == "params_insufficient_history"
    assert out["level_basis"]["params"]["trigger_window_long_atr"]["sample_n"] < 250


def test_a_failed_on_demand_run_keeps_params_unavailable(world, caplog):
    import gcp.database as database

    pdb = world["pdb"]

    def strict(sql, params=None):
        if sql in (job.DAILY_SQL, job.MINUTES_SQL):
            raise RuntimeError("connection reset")
        return pdb.query(sql, params)

    database.query_to_dataframe_strict = strict  # restored by monkeypatch teardown
    out = summarizers.summarize_session_levels(NEW, as_of=SESSION, loader=world["loader"])
    assert _rows(pdb).empty
    sl = SessionLevels.from_basis(out["level_basis"])
    assert sl.long.reason == "params_unavailable" and sl.short.reason == "params_unavailable"
    assert "on-demand calibration of NEWT" in caplog.text
