"""The calibration and sweep scripts read the exchange's date (FEAT-DATA-001, stage 1).

`calibrate-thresholds` runs at 02:00 America/New_York once a quarter, and the
parameter sweep has no scheduler. A run started in the evening took "today"
from the container's UTC date, which is tomorrow: the lookback window, the
``calibration_date`` stamp, the "not in the future" check on ``--as-of`` and
the date ``--apply`` writes to ``exit_config_overrides``.
"""
from __future__ import annotations

import sys
from datetime import timedelta

import pandas as pd
import pytest
import sqlalchemy

import gcp.database as database
import scripts.calibrate_thresholds as calibrate
import scripts.run_param_sweep as param_sweep
from lib.eastern_time import market_today_sql
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock
from tests.scripts.test_calibrate_thresholds import synthetic_bars

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


@four_instants
def test_calibrate_defaults(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, calibrate)
    bound = []

    def recording_read_sql(sql, eng, params=None):
        bound.append(params)
        return pd.DataFrame()

    monkeypatch.setattr(calibrate.pd, "read_sql", recording_read_sql)

    calibrate.fetch_bars("SPY", 90, None)

    assert bound[0]["cutoff"] == eastern - timedelta(days=90)
    assert bound[0]["end_excl"] == eastern + timedelta(days=1)

    stamped = calibrate.calibrate_ticker("TEST", synthetic_bars(n=2000), lookback_days=60)
    assert stamped["calibration_date"] == eastern

    assert calibrate._parse_as_of(eastern.isoformat()) == eastern
    with pytest.raises(SystemExit, match="in the future"):
        calibrate._parse_as_of((eastern + timedelta(days=1)).isoformat())


@four_instants
def test_param_sweep_default_start(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, param_sweep)
    swept = []

    def recording_sweep(ticker, start, end, use_strat, run_id, apply):
        swept.append((ticker, start))

    for name in ("CLOUD_RUN_EXECUTION", "CLOUD_RUN_TASK_INDEX", "CLOUD_RUN_TASK_COUNT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(param_sweep, "sweep_ticker", recording_sweep)
    monkeypatch.setattr(sys, "argv", ["x", "--tickers", "SPY"])

    with pytest.raises(SystemExit) as done:
        param_sweep.main()

    assert done.value.code == 0
    assert swept == [
        ("SPY", (eastern - timedelta(days=param_sweep.DEFAULT_SWEEP_LOOKBACK_DAYS)).isoformat()),
    ]


def test_apply_winner_writes_the_exchange_date(monkeypatch):
    issued = []
    monkeypatch.setattr(database, "execute_sql", lambda sql, params=None: issued.append((sql, params)))
    winner = {
        "stability_score": 0.5, "avg_expectancy_pct": 0.001, "total_trades": 10, "total_folds": 3,
        "call_target": 0.5, "put_target": 0.5, "call_time_stop": 30, "put_time_stop": 30,
        "consecutive_periods": 2,
    }

    param_sweep.apply_winner("SPY", winner, "run-1")

    (sql, params), = issued
    assert sql.count(market_today_sql()) == 1
    assert "CURRENT_DATE" not in sql
    # The helper's text brings a :: cast; the statement keeps exactly the binds it had.
    binds = {"ticker", "call_target", "put_target", "call_time_stop", "put_time_stop",
             "consecutive_periods", "notes"}
    assert set(sqlalchemy.text(sql)._bindparams) == binds
    assert set(params) == binds
