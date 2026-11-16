"""FEAT-STRAT-001 per-ticker params, done_when 5 (offline part): the
premarket print filter reads the ticker's calibrated thresholds.

* Both production callers (gcp/fetchers/fetch_market_data.py nightly and
  gcp/fetchers/fetch_premarket_refresh.py) read the level parameters once
  per run for their whole universe.
* Each writes pre_filter_status and pre_filter_params (the two thresholds'
  value, status, effective_from and run id, and the ATR used) beside the
  snapshot.
* A ticker with no calibrated thresholds gets pre_filter_status
  params_unavailable and NULL excluded counts; unreadable tables give
  level_params_unavailable on every snapshot and the run exits non-zero.
* The level builder refuses such a snapshot (premarket_status
  premarket_unfiltered), the brief says so, and the market summary that
  shows its pre_high and pre_low labels it unfiltered.

The callers run their own SQL against SQLite holding the committed
2026-11-06 bars (tests/gcp/test_premarket_filter_callers.py) and read the
parameter tables created from gcp/schema.sql. The 2026-11-06 values under
production-calibrated thresholds (done_when 5's first half) need the history
calibration against production bars and are not asserted here.
On origin/main and the #1753 head none of the columns, statuses or
parameter reads exist.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lib.strat_levels import (
    PREMARKET_UNFILTERED_NOTE, build_session_levels, format_levels_for_brief,
    premarket_snapshot_from_row,
)
from tests.gcp.test_premarket_filter_callers import _Db
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import ParamsDb, install_level_params, legacy_db

ROOT = Path(__file__).resolve().parents[2]
SESSION = fx.SESSION
EFF = date(2026, 11, 3)


# ── one read per run ─────────────────────────────────────────────────


def _level_param_queries(db: ParamsDb):
    return [q for q in db.queries if "level_param_policy" in q]


def test_nightly_fetcher_reads_the_parameters_once_per_run(monkeypatch):
    from gcp.fetchers import fetch_market_data as fmd

    pdb = install_level_params(monkeypatch, ("SPY", "QQQ", "IWM", "NVDA"))
    seen = {}
    monkeypatch.setattr(fmd, "process_ticker",
                        lambda t, d, k, *, level_params=None: seen.__setitem__(t, level_params))
    monkeypatch.setattr(fmd, "fetch_and_upsert_vix", lambda *a: 0)
    monkeypatch.setattr(fmd, "_verify_post_fetch_rows", lambda *a: None)
    monkeypatch.setattr(sys, "argv", ["fmd", "--tickers", "SPY QQQ IWM NVDA", "--date",
                                      SESSION.isoformat(), "--allow-stale-date",
                                      "--earnings-window-days", "0"])
    fmd.main()
    assert len(_level_param_queries(pdb)) == 1
    assert sorted(seen) == ["IWM", "NVDA", "QQQ", "SPY"]
    assert all(lp.ticker == t and lp.ok("pm_spike_atr") for t, lp in seen.items())


def test_refresh_fetcher_reads_the_parameters_once_per_run(monkeypatch):
    from gcp.fetchers import fetch_premarket_refresh as fpr

    pdb = install_level_params(monkeypatch, ("SPY", "QQQ"))
    seen = {}
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setattr(fpr, "compute_premarket_for_ticker",
                        lambda t, d, k, *, level_params=None: seen.__setitem__(t, level_params))
    monkeypatch.setattr(fpr, "upsert_premarket", lambda rows: len(rows))
    monkeypatch.setattr(sys, "argv", ["fpr", "--tickers", "SPY", "QQQ", "IWM",
                                      "--date", SESSION.isoformat()])
    fpr.main()
    assert len(_level_param_queries(pdb)) == 1
    assert sorted(seen) == ["IWM", "QQQ", "SPY"]
    # IWM has no rows: its parameters are there, every key params_unavailable.
    assert seen["IWM"].status("pm_spike_atr") == "params_unavailable"


@pytest.mark.parametrize("which", ["nightly", "refresh"])
def test_unreadable_tables_write_unfiltered_snapshots_and_exit_non_zero(monkeypatch, which):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd
    from gcp.fetchers import fetch_premarket_refresh as fpr

    def broken(sql, params=None):
        raise RuntimeError("relation ticker_level_params does not exist")

    monkeypatch.setattr(database, "query_to_dataframe_strict", broken)
    seen = {}
    if which == "nightly":
        monkeypatch.setattr(fmd, "process_ticker",
                            lambda t, d, k, *, level_params=None: seen.__setitem__(t, level_params))
        monkeypatch.setattr(fmd, "fetch_and_upsert_vix", lambda *a: 0)
        monkeypatch.setattr(sys, "argv", ["fmd", "--tickers", "SPY QQQ", "--date",
                                          SESSION.isoformat(), "--allow-stale-date",
                                          "--earnings-window-days", "0"])
        main = fmd.main
    else:
        monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
        monkeypatch.setattr(fpr, "compute_premarket_for_ticker",
                            lambda t, d, k, *, level_params=None: seen.__setitem__(t, level_params))
        written = []
        monkeypatch.setattr(fpr, "upsert_premarket", lambda rows: written.append(rows) or 0)
        monkeypatch.setattr(sys, "argv", ["fpr", "--tickers", "SPY", "QQQ",
                                          "--date", SESSION.isoformat()])
        main = fpr.main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert seen == {"SPY": None, "QQQ": None}


# ── what each caller writes ──────────────────────────────────────────


def _nightly_row(monkeypatch, ticker, level_params):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd

    db = _Db(ticker)
    written = []
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    fmd.compute_and_upsert_daily_indicators(ticker, SESSION.isoformat(), level_params=level_params)
    return [r for t, r in written if t == "market_data_daily"][-1]


def _refresh_row(monkeypatch, ticker, level_params):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd
    from gcp.fetchers import fetch_premarket_refresh as fpr

    bars = fx.premarket_bars(ticker)
    minute = pd.DataFrame(
        {"Open": bars["open"].values, "High": bars["high"].values, "Low": bars["low"].values,
         "Close": bars["close"].values, "Volume": bars["volume"].values},
        index=pd.DatetimeIndex(bars["timestamp"]).tz_localize("America/New_York"))
    monkeypatch.setattr(database, "query_to_dataframe", _Db(ticker).query)
    monkeypatch.setattr(fmd, "fetch_minute_data", lambda tk, d, k: minute)
    return fpr.compute_premarket_for_ticker(ticker, SESSION, "key", level_params=level_params)


def _params(ticker, **legacy_kw):
    return legacy_db([ticker], effective_from=EFF, **legacy_kw).load([ticker], SESSION)[ticker]


@pytest.mark.parametrize("writer", [_nightly_row, _refresh_row])
def test_filtered_snapshot_records_its_thresholds(monkeypatch, writer):
    import json

    lp = _params("QQQ", overrides={"pm_spike_atr": 0.7, "pm_stale_print_atr": 0.13})
    row = writer(monkeypatch, "QQQ", lp)
    assert row["pre_filter_status"] == "ok"
    rec = row["pre_filter_params"]
    rec = json.loads(rec) if isinstance(rec, str) else rec
    assert rec["atr_basis"] == "atr_14" and rec["atr"] == pytest.approx(fx.prior_atr("QQQ"))
    assert rec["pm_spike_atr"]["value"] == 0.7 and rec["pm_spike_atr"]["status"] == "ok"
    assert rec["pm_stale_print_atr"]["value"] == 0.13
    assert rec["pm_spike_atr"]["effective_from"] == EFF.isoformat()
    assert rec["pm_spike_atr"]["run_id"] == lp.param("pm_spike_atr").run_id
    assert rec["policy_effective_from"] == "2015-01-02"
    assert isinstance(row["pre_excluded_stale_prints"], int)
    assert isinstance(row["pre_excluded_spikes"], int)


@pytest.mark.parametrize("writer", [_nightly_row, _refresh_row])
def test_no_calibrated_thresholds_give_params_unavailable_and_null_counts(monkeypatch, writer):
    lp = ParamsDb().load(["QQQ"], SESSION)["QQQ"]  # no rows for QQQ
    row = writer(monkeypatch, "QQQ", lp)
    assert row["pre_filter_status"] == "params_unavailable"
    assert row["pre_excluded_stale_prints"] is None and row["pre_excluded_spikes"] is None
    # The unfiltered values are still written, labelled.
    assert row["pre_high"] is not None and row["pre_low"] is not None


@pytest.mark.parametrize("writer", [_nightly_row, _refresh_row])
def test_insufficient_history_thresholds_are_named(monkeypatch, writer):
    lp = _params("QQQ", statuses={"pm_spike_atr": "insufficient_history"})
    row = writer(monkeypatch, "QQQ", lp)
    assert row["pre_filter_status"] == "insufficient_history"
    assert row["pre_excluded_spikes"] is None


@pytest.mark.parametrize("writer", [_nightly_row, _refresh_row])
def test_unreadable_tables_label_the_snapshot(monkeypatch, writer):
    row = writer(monkeypatch, "QQQ", None)
    assert row["pre_filter_status"] == "level_params_unavailable"
    assert row["pre_excluded_stale_prints"] is None and row["pre_excluded_spikes"] is None


# ── readers refuse or label it ───────────────────────────────────────


def test_the_builder_refuses_an_unfiltered_snapshot_and_the_brief_says_so(monkeypatch):
    lp_none = ParamsDb().load(["QQQ"], SESSION)["QQQ"]
    row = _nightly_row(monkeypatch, "QQQ", lp_none)
    snap = premarket_snapshot_from_row(row, SESSION)
    assert snap["pre_filter_status"] == "params_unavailable"
    d = fx.daily("QQQ")
    s = build_session_levels("QQQ", SESSION, d, {"atr_14": fx.prior_atr("QQQ"), "atr_5": None},
                             snap, _params("QQQ"))
    assert s.premarket_status == "premarket_unfiltered" and s.premarket is None
    assert s.reference == pytest.approx(float(d["Close"].iloc[-1]))
    text = format_levels_for_brief(s.to_level_map(), "bullish")
    assert PREMARKET_UNFILTERED_NOTE in text
    assert s.to_basis()["premarket_status"] == "premarket_unfiltered"
    # The same snapshot filtered is accepted.
    ok = premarket_snapshot_from_row(_nightly_row(monkeypatch, "QQQ", _params("QQQ")), SESSION)
    s2 = build_session_levels("QQQ", SESSION, d, {"atr_14": fx.prior_atr("QQQ"), "atr_5": None},
                              ok, _params("QQQ"))
    assert s2.premarket_status == "ok"


@pytest.mark.parametrize("status,labelled", [("params_unavailable", True), (None, True), ("ok", False)])
def test_the_market_summary_labels_unfiltered_premarket(monkeypatch, status, labelled):
    from lib.agents import summarizers

    daily = pd.DataFrame([{"date": "2026-11-05", "close": 650.0, "atr_14": 9.0, "sma_200": 600.0,
                           "ema_20": 640.0, "price_vs_ema20": 0.01}])
    pm = {"pre_high": 660.4, "pre_low": 649.6, "pre_vwap": 655.0, "pre_volume": 1000,
          "gap_pct": 0.5, "pre_range_atr": 1.2}

    def q(sql, params=None):
        if "close IS NOT NULL" in sql:
            return daily
        if "pre_filter_status" in sql:
            # A table without the column: the swallowing reader returns empty.
            return pd.DataFrame() if status is None else pd.DataFrame([{**pm, "pre_filter_status": status}])
        return pd.DataFrame([pm])

    monkeypatch.setattr(summarizers, "_query", q)
    block = summarizers.summarize_market_context("QQQ", as_of=date(2026, 11, 6))["premarket"]
    assert block["pre_high"] == 660.4
    assert block["filtered"] is (not labelled)
    assert (block.get("note") == PREMARKET_UNFILTERED_NOTE) is labelled


def test_refresh_upsert_overwrites_the_filter_status():
    from gcp.fetchers.fetch_premarket_refresh import _upsert_premarket_sql
    sql = _upsert_premarket_sql(True)
    assert "pre_filter_status = EXCLUDED.pre_filter_status" in sql
    assert "pre_excluded_spikes = EXCLUDED.pre_excluded_spikes" in sql
    assert "CAST(:pre_filter_params AS JSONB)" in sql
    assert "pre_high = COALESCE(EXCLUDED.pre_high" in sql


def test_schema_declares_the_filter_columns():
    schema = (ROOT / "gcp" / "schema.sql").read_text()
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_filter_status\s+VARCHAR\(40\)", schema)
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_filter_params\s+JSONB", schema)
