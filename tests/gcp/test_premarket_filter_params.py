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


def _use_bars(monkeypatch, bars):
    """Make the session's premarket bars `bars` (a frame with timestamp, open,
    high, low, close, volume; Eastern wall time) for every writer stand-in."""
    if bars is not None:
        monkeypatch.setattr(fx, "premarket_bars", lambda ticker: bars.copy())


def _failing(query, marker, error):
    def run(sql, params=None):
        if marker in sql:
            raise error
        return query(sql, params)
    return run


def _nightly_row(monkeypatch, ticker, level_params, *, bars=None, bars_error=None):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd

    _use_bars(monkeypatch, bars)
    db = _Db(ticker)
    written = []
    query = db.query if bars_error is None else _failing(
        db.query, "market_data_intraday", bars_error)
    monkeypatch.setattr(database, "query_to_dataframe", query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    fmd.compute_and_upsert_daily_indicators(ticker, SESSION.isoformat(), level_params=level_params)
    return [r for t, r in written if t == "market_data_daily"][-1]


def _refresh_row(monkeypatch, ticker, level_params, *, bars=None, bars_error=None):
    import gcp.database as database
    from gcp.fetchers import fetch_market_data as fmd
    from gcp.fetchers import fetch_premarket_refresh as fpr

    _use_bars(monkeypatch, bars)
    bars = fx.premarket_bars(ticker)
    minute = pd.DataFrame(
        {"Open": bars["open"].values, "High": bars["high"].values, "Low": bars["low"].values,
         "Close": bars["close"].values, "Volume": bars["volume"].values},
        index=pd.DatetimeIndex(bars["timestamp"]).tz_localize("America/New_York"))

    def fetch(tk, d, k):
        if bars_error is not None:
            raise bars_error
        return minute

    monkeypatch.setattr(database, "query_to_dataframe", _Db(ticker).query)
    monkeypatch.setattr(fmd, "fetch_minute_data", fetch)
    return fpr.compute_premarket_for_ticker(ticker, SESSION, "key", level_params=level_params)


def _backfill_row(monkeypatch, ticker, level_params, *, bars=None, bars_error=None):
    """gcp.backfill_ticker.compute_indicators_for_dates on the same stand-in:
    its own SQL against the SQLite tables, and the row it hands to
    upsert_dataframe. It reads the level parameters itself; the stand-in
    answers that read with `level_params` (None: the tables are unreadable)."""
    import gcp.database as database
    import lib.strat_levels as sl
    from gcp import backfill_ticker as bt

    _use_bars(monkeypatch, bars)
    db = _Db(ticker)
    written = []

    def load(query_fn, tickers, session_date):
        if level_params is None:
            raise sl.LevelParamsUnavailable("relation ticker_level_params does not exist")
        return {ticker.upper(): level_params}

    strict = db.query if bars_error is None else _failing(
        db.query, "market_data_intraday", bars_error)
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    monkeypatch.setattr(sl, "load_level_params", load)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    bt.compute_indicators_for_dates(ticker, [SESSION])
    return [r for t, r in written if t == "market_data_daily"][-1]


WRITERS = [_nightly_row, _refresh_row, _backfill_row]


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
    # FEAT-PLAYBOOK-001 B8: a rejected extreme is cleared, not kept, so the
    # extremes are overwritten (this line pinned the COALESCE until then).
    assert "pre_high = EXCLUDED.pre_high" in sql
    assert "pre_vwap = COALESCE(EXCLUDED.pre_vwap" in sql


def test_schema_declares_the_filter_columns():
    schema = (ROOT / "gcp" / "schema.sql").read_text()
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_filter_status\s+VARCHAR\(40\)", schema)
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_filter_params\s+JSONB", schema)


# FEAT-PLAYBOOK-001 B8: the writers record the extreme rules and clear a
# rejected extreme (spec 2026-11-16, Design 4; plan Task 7).

import hashlib  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402

from tests.gcp.test_premarket_filter_callers import _sql_param  # noqa: E402

# gcp/schema.sql as it was before this task (sha256 of the file's bytes).
SCHEMA_SHA256 = "b017fbd2fadb5dbfd39b20953451c5a90f46720c4c860c3ae9b00e66afcba55f"

# What an earlier run left in the session's market_data_daily row.
STORED = {"pre_high": 660.398, "pre_low": 649.62, "pre_range_atr": 0.9876, "pre_vwap": 655.0,
          "pre_volume": 1000, "gap_pct": 1.37}
CLEARED = ("pre_high", "pre_low", "pre_range_atr")


def _session_bars(rows):
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(SESSION.isoformat() + " " + frame["timestamp"])
    return frame


# (a) Every bar under one round lot (thin-bar-v1).
ALL_THIN = _session_bars([
    ("08:00", 655.10, 655.40, 655.00, 655.30, 50),
    ("08:01", 655.30, 655.60, 655.20, 655.50, 50),
    ("08:02", 655.50, 655.70, 655.30, 655.40, 50),
])
# (b) One bar whose open and close are the prior close 647.05 to the cent, a
# little away from it: with pm_stale_print_atr calibrated to zero rule (a)
# drops both, and the bar's lone high and low confirm nothing.
UNCONFIRMED = _session_bars([("08:00", 647.054, 650.00, 645.00, 647.054, 5000)])
REJECTED = {
    "all_bars_thin": (ALL_THIN, {}),
    "unconfirmed": (UNCONFIRMED, {"pm_stale_print_atr": 0.0}),
}


def _record(row):
    rec = row["pre_filter_params"]
    return json.loads(rec) if isinstance(rec, str) else rec


def _null(value):
    return value is None or (isinstance(value, float) and value != value)


class _RefreshStore:
    """market_data_daily in SQLite behind the engine upsert_premarket asks
    for. It runs the refresh's own statement; SQLite has no JSONB, so that
    one cast is taken off the statement before it runs."""

    COLUMNS = ("pre_high", "pre_low", "pre_vwap", "pre_volume", "gap_pct", "pre_range_atr",
               "pre_fetched_at", "pre_excluded_stale_prints", "pre_excluded_spikes",
               "pre_filter_status", "pre_filter_params")

    def __init__(self, ticker, stored):
        self.statements = []
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE market_data_daily (ticker TEXT, date TEXT, "
            + ", ".join(self.COLUMNS) + ", PRIMARY KEY (ticker, date))")
        if stored is not None:
            self.conn.execute(
                f"INSERT INTO market_data_daily (ticker, date, {', '.join(stored)}) "
                f"VALUES (?, ?, {', '.join('?' for _ in stored)})",
                [ticker, SESSION.isoformat(), *stored.values()])

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append(text)
        self.conn.execute(text.replace("CAST(:pre_filter_params AS JSONB)", ":pre_filter_params"),
                          {k: _sql_param(v) for k, v in (params or {}).items()})

    def row(self, ticker):
        cur = self.conn.execute(
            f"SELECT {', '.join(self.COLUMNS)} FROM market_data_daily WHERE ticker = ? AND date = ?",
            [ticker, SESSION.isoformat()])
        found = cur.fetchone()
        return None if found is None else dict(zip(self.COLUMNS, found))


def _refresh_write(monkeypatch, ticker, rows, stored):
    """upsert_premarket(rows) against a table holding `stored`; the store."""
    import gcp.database as database
    from gcp.fetchers import fetch_premarket_refresh as fpr

    store = _RefreshStore(ticker, stored)
    monkeypatch.setattr(database, "get_engine", lambda: store)
    monkeypatch.setattr(fpr, "_has_provenance_columns", lambda eng: True)
    fpr.upsert_premarket(rows)
    return store


def _stored_after(monkeypatch, writer, ticker, level_params, bars):
    """The session's market_data_daily row after `writer` recomputes it from
    `bars`, starting from STORED, and the statements the refresh issued.

    The nightly and the backfill write through gcp.database.upsert_dataframe,
    which sets every column of the frame it is handed from EXCLUDED
    (update_cols defaults to every non-key column), so the row afterwards is
    STORED overlaid with the handed row. The refresh's own statement runs in
    SQLite."""
    row = writer(monkeypatch, ticker, level_params, bars=bars)
    if writer is _refresh_row:
        store = _refresh_write(monkeypatch, ticker, [row], STORED)
        return row, store.row(ticker), store.statements
    after = dict(STORED)
    after.update({k: (None if _null(v) else v) for k, v in row.items()})
    return row, after, []


@pytest.mark.parametrize("writer", WRITERS)
def test_written_row_holds_the_rule_blocks(monkeypatch, writer):
    lp = _params("QQQ", overrides={"pm_spike_atr": 0.7, "pm_stale_print_atr": 0.13})
    row = writer(monkeypatch, "QQQ", lp)
    rec = _record(row)
    assert rec["confirmed"]["rule"] == "two-bars-or-body-v1"
    assert rec["confirmed"]["stale_close_reports"] == {
        "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 647.05}
    assert rec["confirmed"]["reason"] is None
    assert rec["confirmed"]["raw_high"] == pytest.approx(row["pre_high"]) or (
        rec["confirmed"]["high_bars_above"] >= 1)
    assert rec["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 0}
    # prior-close-print-v1 (FEAT-PLAYBOOK-001, PC3): rule (a) has already
    # dropped the 2026-11-06 prints at 647.05, so this rule drops none.
    assert rec["confirmed"]["prior_close_prints"] == {
        "rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25,
        "open": 0, "high": 0, "low": 0, "close": 0, "bars": 0, "prior_close": 647.05}
    # Beside the existing threshold records.
    assert rec["pm_spike_atr"]["value"] == 0.7 and rec["pm_spike_atr"]["status"] == "ok"
    assert rec["pm_stale_print_atr"]["value"] == 0.13
    assert rec["atr_basis"] == "atr_14"

    # A bar that opens and closes at the prior close with its high 8.65
    # above it: rule (a) keeps it (its midpoint is the prior close), the
    # stale rule keeps it (it opens there), and prior-close-print-v1 drops
    # its open, low and close. Each writer records that in the row it writes.
    bars = _session_bars([
        ("08:00", 655.10, 655.40, 655.00, 655.30, 5000),
        ("08:01", 655.30, 655.60, 655.20, 655.50, 5000),
        ("08:02", 647.05, 655.70, 647.05, 647.05, 5000),   # opens and closes at the prior close
        ("08:03", 655.50, 655.70, 655.30, 655.40, 5000),
    ])
    row = writer(monkeypatch, "QQQ", lp, bars=bars)
    rec = _record(row)
    assert row["pre_filter_status"] == "ok"
    assert row["pre_low"] == pytest.approx(655.10)          # 647.05 on the merge base
    assert rec["confirmed"]["prior_close_prints"] == {
        "rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25,
        "open": 1, "high": 0, "low": 1, "close": 1, "bars": 1, "prior_close": 647.05}
    assert rec["confirmed"]["stale_close_reports"] == {
        "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 647.05}


def test_snapshot_drops_a_prior_close_print():
    """FEAT-PLAYBOOK-001 prior-close-print-v1, PC1b, through
    gcp.fetchers.fetch_market_data.premarket_snapshot, the path the nightly
    and the 08:20 refresh take: the QQQ bars of 2026-11-16 written in
    tests/lib/test_premarket_print_filter.py, with the 07:40 ET bar whose
    open-close midpoint is at the prior close, under thresholds that are ok.
    On the merge base 6243496db pre_high is 679.89 there."""
    from datetime import datetime, time, timezone

    from gcp.fetchers import fetch_market_data as fmd
    from lib.eastern_time import eastern_bounds_utc
    from tests.lib.test_premarket_print_filter import QQQ_0740, QQQ_ROWS

    day = date(2026, 11, 16)

    def utc(hhmm):
        at = time(*map(int, hhmm.split(":")))
        return eastern_bounds_utc(day, at, at)[0]

    bars = pd.DataFrame([
        {"ts": utc(t), "open": o, "high": h, "low": lo, "close": c, "volume": v}
        for (t, o, h, lo, c, v) in sorted(QQQ_ROWS + [QQQ_0740])])
    lp = legacy_db(["QQQ"], overrides={"pm_stale_print_atr": 0.0371, "pm_spike_atr": 1.0725}).load(
        ["QQQ"], day)["QQQ"]
    snapshot = fmd.premarket_snapshot(
        "QQQ", day, bars, {"close": 679.89, "open": 679.89, "atr_14": 16.34, "atr_5": 16.34}, lp,
        datetime(2026, 11, 16, 13, 20, tzinfo=timezone.utc))
    assert snapshot["pre_filter_status"] == "ok"
    assert snapshot["pre_high"] == pytest.approx(675.30)
    rec = snapshot["pre_filter_params"]
    rec = json.loads(rec) if isinstance(rec, str) else rec
    assert rec["confirmed"]["prior_close_prints"]["bars"] == 1


@pytest.mark.parametrize("writer", WRITERS)
def test_unreadable_parameters_leave_the_rule_blocks_alone(monkeypatch, writer):
    """With the parameter tables unreadable there is no threshold record; the
    extreme rules still ran (they need no threshold) and are recorded."""
    row = writer(monkeypatch, "QQQ", None)
    assert row["pre_filter_status"] == "level_params_unavailable"
    rec = _record(row)
    assert set(rec) == {"confirmed", "thin"}
    assert rec["confirmed"]["rule"] == "two-bars-or-body-v1"
    assert rec["thin"]["rule"] == "thin-bar-v1"


@pytest.mark.parametrize("writer", WRITERS)
@pytest.mark.parametrize("reason", sorted(REJECTED))
def test_writers_clear_rejected_extremes(monkeypatch, writer, reason):
    bars, overrides = REJECTED[reason]
    lp = _params("QQQ", overrides=overrides)
    row, after, statements = _stored_after(monkeypatch, writer, "QQQ", lp, bars)
    # The row handed to the write holds None for the three columns ...
    for column in CLEARED:
        assert column in row and _null(row[column]), column
    assert row["pre_filter_status"] == "ok"
    assert _record(row)["confirmed"]["reason"] == reason
    # ... and the stored row holds NULL afterwards, never the earlier prices.
    for column in CLEARED:
        assert after[column] is None, column
    assert _record(after)["confirmed"]["reason"] == reason
    assert after["pre_vwap"] is not None and after["pre_vwap"] != STORED["pre_vwap"]
    if writer is _refresh_row:
        (sql,) = statements
        for column in CLEARED:
            assert f"{column} = EXCLUDED.{column}" in sql
            assert f"COALESCE(EXCLUDED.{column}" not in sql
        for column in ("pre_vwap", "pre_volume", "gap_pct"):
            assert f"{column} = COALESCE(EXCLUDED.{column}, market_data_daily.{column})" in sql


EMPTY_BARS = _session_bars([("08:00", 655.10, 655.40, 655.00, 655.30, 500)]).iloc[0:0]


@pytest.mark.parametrize("writer", WRITERS)
@pytest.mark.parametrize("case", ["no_bars", "error"])
def test_a_writer_that_could_not_compute_leaves_the_row(monkeypatch, writer, case):
    """No bars fetched, or the read failing, is unavailable input and not a
    rejected value: none of the three columns is written."""
    kw = {"bars": EMPTY_BARS} if case == "no_bars" else {"bars_error": ConnectionError("vendor down")}
    lp = _params("QQQ")
    if writer is _refresh_row:
        if case == "no_bars":
            rows = [r for r in [writer(monkeypatch, "QQQ", lp, **kw)] if r]
        else:
            with pytest.raises(ConnectionError):
                writer(monkeypatch, "QQQ", lp, **kw)
            rows = []
        assert rows == []
        store = _refresh_write(monkeypatch, "QQQ", rows, STORED)
        assert store.statements == []
        assert {c: store.row("QQQ")[c] for c in CLEARED} == {c: STORED[c] for c in CLEARED}
        return
    if writer is _backfill_row and case == "error":
        # The backfill's bar read is strict: the run ends as raised, before
        # the date's row is written at all.
        with pytest.raises(ConnectionError):
            writer(monkeypatch, "QQQ", lp, **kw)
        return
    row = writer(monkeypatch, "QQQ", lp, **kw)
    for column in CLEARED + ("pre_vwap", "pre_filter_status", "pre_filter_params"):
        assert column not in row, column


def test_refresh_keeps_a_row_with_only_a_vwap(monkeypatch):
    snapshot = {"ticker": "QQQ", "date": SESSION, "pre_high": None, "pre_low": None,
                "pre_vwap": 655.25, "pre_volume": None, "gap_pct": None, "pre_range_atr": None,
                "pre_fetched_at": None, "pre_excluded_stale_prints": 0, "pre_excluded_spikes": 0,
                "pre_filter_status": "ok",
                "pre_filter_params": json.dumps({"confirmed": {"reason": "all_bars_thin"}})}
    store = _refresh_write(monkeypatch, "QQQ", [snapshot], None)
    assert len(store.statements) == 1
    row = store.row("QQQ")
    assert row["pre_vwap"] == 655.25
    assert row["pre_high"] is None and row["pre_low"] is None and row["pre_range_atr"] is None
    assert row["pre_filter_status"] == "ok"


def test_refresh_snapshot_and_statement_carry_the_range(monkeypatch):
    """The refresh did not write pre_range_atr before; it now writes the
    snapshot's own value, so a cleared extreme cannot leave an earlier range."""
    from gcp.fetchers import fetch_premarket_refresh as fpr

    assert "pre_range_atr" in fpr._UPSERT_KEYS
    row = _refresh_row(monkeypatch, "QQQ", _params("QQQ"))
    assert row["pre_range_atr"] == pytest.approx(
        round((row["pre_high"] - row["pre_low"]) / fx.prior_atr("QQQ"), 4))
    for with_provenance in (True, False):
        assert "pre_range_atr = EXCLUDED.pre_range_atr" in fpr._upsert_premarket_sql(with_provenance)


def test_schema_is_unchanged():
    path = ROOT / "gcp" / "schema.sql"
    schema = path.read_text()
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_filter_params\s+JSONB", schema)
    assert re.search(r"ADD COLUMN IF NOT EXISTS pre_range_atr\s+DOUBLE PRECISION", schema)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCHEMA_SHA256


def test_null_extremes_build_levels_without_premarket_rungs(monkeypatch):
    """A morning with no confirmed extreme reaches the builder and the brief:
    a snapshot that is filtered ('ok'), has a VWAP and has no high or low."""
    d = fx.daily("QQQ")
    snap = premarket_snapshot_from_row(
        {"pre_high": None, "pre_low": None, "pre_vwap": 655.25, "gap_pct": 1.2,
         "pre_filter_status": "ok"}, SESSION)
    assert snap is not None and snap["pre_high"] is None and snap["pre_low"] is None
    s = build_session_levels("QQQ", SESSION, d, {"atr_14": fx.prior_atr("QQQ"), "atr_5": None},
                             snap, _params("QQQ"))
    basis = s.to_basis()
    names = {c["name"] for side in ("long", "short") for c in basis[side]["candidates"]}
    names |= {a for side in ("long", "short") for c in basis[side]["candidates"]
              for a in c.get("aliases", ())}
    assert "PMK_H" not in names and "PMK_L" not in names
    for side in ("long", "short"):
        trigger = basis[side]["trigger"]
        assert trigger is None or trigger["name"] not in ("PMK_H", "PMK_L")

    frame = fx.loader_frame("QQQ")
    session_row = frame.index[-1]
    frame.loc[session_row, ["pre_high", "pre_low"]] = float("nan")
    assert frame.loc[session_row, "pre_filter_status"] == "ok"
    assert frame.loc[session_row, "pre_vwap"] == frame.loc[session_row, "pre_vwap"]
    out = fx.run_brief(monkeypatch, "QQQ", frame)
    assert out.get("status") != "PLAYBOOK_FAILED"
    brief_names = {c["name"] for side in ("long", "short")
                   for c in out["level_basis"][side]["candidates"]}
    assert "PMK_H" not in brief_names and "PMK_L" not in brief_names
