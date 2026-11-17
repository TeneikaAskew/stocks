"""The premarket columns of market_data_daily, computed in one function and
recomputed from stored bars (FEAT-DATA-001): `premarket_snapshot` and the
--recompute-premarket mode of gcp/fetchers/fetch_market_data.py.

Hermetic: every read is answered in the test and nothing reaches a vendor.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import numpy as np
import pandas as pd
import pytest

import gcp.database as database
from gcp.fetchers import fetch_market_data as fmd
from tests.lib.level_params_fixtures import legacy_db

UTC = timezone.utc
READ_AT = datetime(2026, 11, 14, 12, 0, 0, 123456, tzinfo=UTC)
PRIOR = {"close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}


def premarket_bars(day: date, inserted: str = "2026-11-14") -> pd.DataFrame:
    """330 bars, 04:00 to 09:29 Eastern: open 100.0, high 100.5, low 99.5,
    close 100.0, volume 1000."""
    from lib.eastern_time import eastern_bounds_utc

    start, end = eastern_bounds_utc(day, time(4), time(9, 30))
    ts = pd.date_range(start, end, freq="1min", inclusive="left")
    return pd.DataFrame({
        "ts": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
        "volume": 1000, "inserted_at": pd.Timestamp(inserted, tz="UTC"),
    })


def daily_history(last: date, sessions: int = 40) -> pd.DataFrame:
    """Business days ending on *last*: open 99.0, high 100.0, low 98.0,
    close 99.0, so every true range is 2.0."""
    days = pd.bdate_range(end=last, periods=sessions)
    return pd.DataFrame({
        "date": [d.date() for d in days], "Open": 99.0, "High": 100.0, "Low": 98.0,
        "Close": 99.0, "Volume": 1_000_000,
    })


# The extreme rules' record of the fixture session (FEAT-PLAYBOOK-001 B8):
# 330 bars of 1,000 shares between 99.5 and 100.5, each reached by more than
# one bar, with the prior close 99.0. The writers put it in pre_filter_params.
RULE_BLOCKS = {
    "confirmed": {"rule": "two-bars-or-body-v1", "raw_high": 100.5, "raw_low": 99.5,
                  "high_bars_above": 0, "low_bars_below": 0,
                  "stale_close_reports": {"rule": "stale-close-report-v1", "high": 0, "low": 0,
                                          "prior_close": 99.0},
                  "reason": None},
    "thin": {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 0},
}


# ── one function for the computation ──────────────────────────────────


def test_the_snapshot_is_the_one_place(monkeypatch):
    from lib.strat_levels import premarket_filter_inputs

    day = date(2026, 10, 6)
    params = legacy_db(("SPY", "QQQ")).load(["SPY", "QQQ"], day)["SPY"]
    snapshot = fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, params, READ_AT)

    assert list(snapshot) == list(fmd.PREMARKET_COLUMNS)
    assert snapshot == {
        "pre_high": 100.5,
        "pre_low": 99.5,
        "pre_vwap": 100.0,
        "pre_volume": 330000,
        "gap_pct": 1.0101,
        "pre_range_atr": 0.5,
        "pre_fetched_at": READ_AT,
        "pre_excluded_stale_prints": 0,
        "pre_excluded_spikes": 0,
        "pre_filter_status": "ok",
        # The threshold record with the extreme rules' record beside it
        # (FEAT-PLAYBOOK-001 B8; the threshold record alone until then).
        "pre_filter_params": {
            **premarket_filter_inputs(params, {"atr_14": 2.0, "atr_5": 2.0})["params"],
            **RULE_BLOCKS},
    }

    # A session before the ticker's first parameter row: unfiltered, and it says so.
    early = date(2026, 9, 24)
    later_params = legacy_db(("SPY", "QQQ"), effective_from=date(2026, 10, 1)).load(
        ["SPY", "QQQ"], early)["SPY"]
    unfiltered = fmd.premarket_snapshot(
        "SPY", early, premarket_bars(early), PRIOR, later_params, READ_AT)
    assert unfiltered["pre_filter_status"] == "params_unavailable"
    assert unfiltered["pre_range_atr"] is None
    assert unfiltered["pre_excluded_stale_prints"] is None
    assert unfiltered["pre_excluded_spikes"] is None
    assert [unfiltered[c] for c in ("pre_high", "pre_low", "pre_vwap", "pre_volume",
                                    "gap_pct")] == [100.5, 99.5, 100.0, 330000, 1.0101]
    assert unfiltered["pre_fetched_at"] == READ_AT

    # The run could not read the parameter tables: what the nightly records.
    unread = fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, None, READ_AT)
    assert unread["pre_filter_status"] == "level_params_unavailable"
    # No threshold record; the extreme rules ran and are recorded (None until
    # FEAT-PLAYBOOK-001 B8).
    assert unread["pre_filter_params"] == RULE_BLOCKS

    empty = premarket_bars(day).iloc[0:0]
    assert fmd.premarket_snapshot("SPY", day, empty, PRIOR, params, READ_AT) is None

    # Bars outside the premarket window only: no snapshot.
    session_only = premarket_bars(day)
    session_only["ts"] = session_only["ts"] + pd.Timedelta(hours=6)
    assert fmd.premarket_snapshot("SPY", day, session_only, PRIOR, params, READ_AT) is None

    import lib.indicators as indicators

    failure = KeyError("close")

    def broken(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(indicators, "calculate_premarket_context", broken)
    with pytest.raises(KeyError) as caught:
        fmd.premarket_snapshot("SPY", day, premarket_bars(day), PRIOR, params, READ_AT)
    assert caught.value is failure


def test_prior_session_inputs():
    from lib.indicators import add_all_indicators

    df = daily_history(date(2026, 10, 6))
    enriched = add_all_indicators(df, close_col="Close")
    assert fmd.prior_session_inputs(df, enriched) == {
        "close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}

    holed = df.copy()
    holed.loc[holed.index[-2], "Close"] = np.nan
    assert fmd.prior_session_inputs(holed, enriched)["close"] is None
    assert fmd.prior_session_inputs(holed, enriched)["open"] == 99.0

    assert fmd.prior_session_inputs(df.iloc[-1:], enriched.iloc[-1:]) == {
        "close": None, "open": None, "atr_14": None, "atr_5": None}

    # A frame add_all_indicators gave no ATR column: no ATR, not an error.
    no_atr = enriched.drop(columns=["ATR14", "ATR5"])
    assert fmd.prior_session_inputs(df, no_atr) == {
        "close": 99.0, "open": 99.0, "atr_14": None, "atr_5": None}

    with pytest.raises(KeyError):
        fmd.prior_session_inputs(df.drop(columns=["Close"]), enriched)


def test_the_nightly_calls_the_snapshot(monkeypatch):
    day = date(2026, 10, 6)
    params = legacy_db(("SPY", "QQQ")).load(["SPY", "QQQ"], day)["SPY"]
    history = daily_history(day)
    bars = premarket_bars(day).drop(columns=["inserted_at"])

    def query(sql, params=None):
        if "FROM market_data_intraday" in sql:
            return bars
        assert "FROM market_data_daily" in sql
        return history.iloc[::-1].reset_index(drop=True)  # newest first, as the query orders

    calls = []
    real = fmd.premarket_snapshot

    def recording(*args, **kwargs):
        calls.append(real(*args, **kwargs))
        return calls[-1]

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append((table, df.iloc[0].to_dict())))
    monkeypatch.setattr(fmd, "premarket_snapshot", recording)

    fmd.compute_and_upsert_daily_indicators("SPY", "2026-10-06", level_params=params)

    assert len(calls) == 1
    (table, row), = written
    assert table == "market_data_daily"
    for column in fmd.PREMARKET_COLUMNS:
        assert row[column] == calls[0][column], column
    assert row["pre_filter_status"] == "ok"
    assert row["pre_high"] == 100.5
    assert row["pre_range_atr"] == 0.5


def test_the_nightly_keeps_a_stored_price_when_the_new_one_is_none(monkeypatch):
    """The nightly's own write rule: pre_vwap, pre_volume and gap_pct are set
    only when the new value is not None; the provenance columns always. Since
    FEAT-PLAYBOOK-001 B8 the high, the low and the range are written as
    computed, None included, so a rejected extreme is cleared and a range no
    snapshot gives (here: no ATR, the parameters were unreadable) does not
    stay from an earlier run."""
    day = date(2026, 10, 6)
    history = daily_history(day)
    bars = premarket_bars(day).drop(columns=["inserted_at"])

    def query(sql, params=None):
        return bars if "FROM market_data_intraday" in sql else history.iloc[::-1].reset_index(drop=True)

    written = []
    monkeypatch.setattr(database, "query_to_dataframe", query)
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: written.append(df.iloc[0].to_dict()))
    fmd.compute_and_upsert_daily_indicators("SPY", "2026-10-06", level_params=None)

    (row,) = written
    assert "pre_range_atr" in row and pd.isna(row["pre_range_atr"])   # None: written, clears
    assert row["pre_filter_status"] == "level_params_unavailable"
    assert row["pre_excluded_spikes"] is None    # provenance: always written
    assert row["pre_filter_params"] == RULE_BLOCKS
    assert row["pre_high"] == 100.5


# ── --recompute-premarket: flags, selection, the three reads, the dry run ──

import csv  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402

from gcp import bar_recompute as br  # noqa: E402
from tests.lib.level_params_fixtures import (  # noqa: E402
    LEGACY_1753_VALUES, ParamsDb, install_level_params,
)

TODAY = date(2026, 11, 14)
RUN_ID = "fetch-market-data-test1"
PARAMS_RUN = "00000000-0000-0000-0000-00000000a001"
OCT_6, SEP_24 = date(2026, 10, 6), date(2026, 9, 24)

SELECTED_COLUMNS = [
    "ticker", "date", "close", "pre_high", "pre_low", "pre_vwap", "pre_volume", "gap_pct",
    "pre_range_atr", "pre_fetched_at", "pre_excluded_stale_prints", "pre_excluded_spikes",
    "pre_filter_status", "pre_filter_params", "pre_recompute_run",
]


def _collapse(text: str) -> str:
    return " ".join(text.split())


def stored_row(ticker: str, day: date, **overrides) -> dict:
    record = {
        "ticker": ticker, "date": day, "close": 99.0, "pre_high": 100.25, "pre_low": 99.75,
        "pre_vwap": 100.01, "pre_volume": 300000, "gap_pct": 0.9, "pre_range_atr": None,
        "pre_fetched_at": None, "pre_excluded_stale_prints": None,
        "pre_excluded_spikes": None, "pre_filter_status": None, "pre_filter_params": None,
        "pre_recompute_run": None,
    }
    record.update(overrides)
    return record


def stored_rows() -> list[dict]:
    return [
        stored_row("QQQ", SEP_24),
        stored_row("QQQ", OCT_6),
        stored_row("SPY", SEP_24, pre_range_atr=0.4),
        stored_row("SPY", OCT_6),
    ]


def stored_premarket_bars() -> dict:
    qqq = premarket_bars(SEP_24)
    qqq.loc[100, "inserted_at"] = pd.Timestamp("2026-09-24 21:00", tz="UTC")
    return {
        ("SPY", OCT_6): premarket_bars(OCT_6, inserted="2026-10-07"),
        ("SPY", SEP_24): premarket_bars(SEP_24, inserted="2026-11-14"),
        ("QQQ", SEP_24): qqq,
    }


class Reader:
    """A strict reader that answers by SQL text and records each call."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, sql, params=None, timeout_s=None):
        assert timeout_s is None
        self.calls.append((sql, params))
        for marker, answer in self.answers:
            if marker in sql:
                return answer(sql, params)
        raise AssertionError(f"no answer for: {_collapse(sql)[:120]}")

    def of(self, marker: str) -> list[tuple[str, dict | None]]:
        return [call for call in self.calls if marker in call[0]]


def schema_ready(_sql=None, _params=None) -> pd.DataFrame:
    return pd.DataFrame({
        "table_name": ["bar_recompute_ledger", "signal_alerts", "trades", "market_data_daily"],
        "column_name": ["run_id", "exit_recompute_run", "exit_recompute_run",
                        "pre_recompute_run"],
    })


def premarket_reader(selected: list[dict] | None = None, bars: dict | None = None,
                     history_sessions: int = 40) -> Reader:
    selected = stored_rows() if selected is None else selected
    bars = stored_premarket_bars() if bars is None else bars

    def selection(_sql, params):
        chosen = [r for r in selected if r["ticker"] in params["tickers"]
                  and params["first"] <= r["date"] <= params["last"]]
        return pd.DataFrame(chosen, columns=SELECTED_COLUMNS)

    def daily(_sql, params):
        frame = daily_history(OCT_6, history_sessions)
        return frame[(frame["date"] >= params["lo"]) & (frame["date"] <= params["hi"])]

    def bar_read(_sql, params):
        empty = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume",
                                      "inserted_at"])
        frames = [frame for (ticker, _day), frame in bars.items() if ticker == params["t"]]
        if not frames:
            return empty
        every = pd.concat(frames, ignore_index=True)
        windows = [(params[f"s{i}"], params[f"e{i}"])
                   for i in range(sum(1 for k in params if k.startswith("s")))]
        inside = pd.Series(False, index=every.index)
        for start, end in windows:
            inside |= (every["ts"] >= start) & (every["ts"] < end)
        return every[inside].sort_values("ts").reset_index(drop=True) if inside.any() else empty

    return Reader([("information_schema.columns", schema_ready),
                   ("FROM market_data_intraday", bar_read),
                   ('AS "Open"', daily),
                   ("pre_recompute_run", selection)])


class NoTransactionEngine:
    def begin(self):
        raise AssertionError("a dry run entered a transaction")

    def connect(self):
        raise AssertionError("a dry run opened a connection")


@pytest.fixture
def premarket_run(monkeypatch, tmp_path):
    """Run fmd.main() in --recompute-premarket mode over the fixture: reads
    answered by SQL text, level parameters effective from 2026-10-01, the
    clock fixed, and no vendor, transaction or bucket."""

    def no_http(*_args, **_kwargs):
        raise AssertionError("an HTTP request")

    class RecordingEnviron(dict):
        """os.environ for one run, recording each name that is read."""

        def __init__(self, *args):
            super().__init__(*args)
            self.asked: list[str] = []

        def get(self, key, default=None):
            self.asked.append(key)
            return super().get(key, default)

        def __getitem__(self, key):
            self.asked.append(key)
            return super().__getitem__(key)

        def __contains__(self, key):
            self.asked.append(key)
            return super().__contains__(key)

    def run(*argv: str, reader: Reader | None = None, report_dir: bool = True,
            params_db: ParamsDb | None = None,
            record_environ: bool = False) -> tuple[int, Reader]:
        reader = premarket_reader() if reader is None else reader
        monkeypatch.setattr(database, "query_to_dataframe_strict", reader)
        monkeypatch.setattr(database, "query_to_dataframe",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("the swallowing reader was used")))
        if params_db is None:
            params_db = ParamsDb()
            for ticker in ("SPY", "QQQ"):
                params_db.write(ticker, LEGACY_1753_VALUES, effective_from=date(2026, 10, 1),
                                run_id=PARAMS_RUN)
        install_level_params(monkeypatch, ("SPY", "QQQ"), db=params_db)
        run.params_db = params_db
        monkeypatch.setattr(database, "get_engine", lambda: NoTransactionEngine())
        monkeypatch.setattr(fmd.requests, "get", no_http)
        monkeypatch.setattr(fmd, "market_today", lambda: TODAY)
        monkeypatch.setattr(fmd, "utc_now", lambda: READ_AT)
        monkeypatch.delenv("GCS_BUCKET", raising=False)
        monkeypatch.setenv("CLOUD_RUN_EXECUTION", RUN_ID)
        tail = ["--report-dir", str(tmp_path)] if report_dir else []
        monkeypatch.setattr(sys, "argv", ["fetch_market_data", *argv, *tail])
        if record_environ:
            run.environ = RecordingEnviron(fmd.os.environ)
            monkeypatch.setattr(fmd.os, "environ", run.environ)
        return fmd.main(), reader

    return run


def premarket_report(tmp_path, run_id: str = RUN_ID):
    folder = tmp_path / "bar-recompute" / "v1" / "daily-premarket" / run_id
    with open(folder / "rows.csv", newline="") as handle:
        table = list(csv.DictReader(handle))
    return table, json.loads((folder / "summary.json").read_text())


WINDOW = ("--from", "2026-09-24", "--to", "2026-10-06")

OK_THRESHOLDS = (
    '{"atr": 2.0, "atr_basis": "atr_14", '
    '"pm_spike_atr": {"effective_from": "2026-10-01", "run_id": "' + PARAMS_RUN + '", '
    '"status": "ok", "value": 0.5}, '
    '"pm_stale_print_atr": {"effective_from": "2026-10-01", "run_id": "' + PARAMS_RUN + '", '
    '"status": "ok", "value": 0.1}, "policy_effective_from": "2015-01-02"}'
)
UNAVAILABLE_THRESHOLDS = (
    '{"atr": 2.0, "atr_basis": "atr_14", '
    '"pm_spike_atr": {"effective_from": null, "run_id": null, '
    '"status": "params_unavailable", "value": null}, '
    '"pm_stale_print_atr": {"effective_from": null, "run_id": null, '
    '"status": "params_unavailable", "value": null}, "policy_effective_from": "2015-01-02"}'
)
# What the recompute writes: the threshold record with the extreme rules'
# record beside it (FEAT-PLAYBOOK-001 B8), as the report prints it.
OK_PARAMS = json.dumps({**json.loads(OK_THRESHOLDS), **RULE_BLOCKS}, sort_keys=True)
UNAVAILABLE_PARAMS = json.dumps({**json.loads(UNAVAILABLE_THRESHOLDS), **RULE_BLOCKS},
                                sort_keys=True)
READ_AT_TEXT = "2026-11-14T12:00:00.123456+00:00"

OLD = {
    "old_pre_high": "100.25", "old_pre_low": "99.75", "old_pre_vwap": "100.01",
    "old_pre_volume": "300000", "old_gap_pct": "0.9", "old_pre_range_atr": "",
    "old_pre_fetched_at": "", "old_pre_excluded_stale_prints": "",
    "old_pre_excluded_spikes": "", "old_pre_filter_status": "", "old_pre_filter_params": "",
}
NO_NEW = {f"new_{c}": "" for c in fmd.PREMARKET_COLUMNS}

EXPECTED_TABLE = [
    {"ticker": "QQQ", "session_date": "2026-09-24", "row_key": "2026-09-24", **OLD, **NO_NEW,
     "changed": "", "status": "unproven_rows", "bars_rows": "", "bars_sha256": "",
     "written": "false"},
    {"ticker": "QQQ", "session_date": "2026-10-06", "row_key": "2026-10-06", **OLD, **NO_NEW,
     "changed": "", "status": "no_bars", "bars_rows": "", "bars_sha256": "",
     "written": "false"},
    {"ticker": "SPY", "session_date": "2026-09-24", "row_key": "2026-09-24",
     **{**OLD, "old_pre_range_atr": "0.4"},
     "new_pre_high": "100.5", "new_pre_low": "99.5", "new_pre_vwap": "100.0",
     "new_pre_volume": "330000", "new_gap_pct": "1.0101", "new_pre_range_atr": "",
     "new_pre_fetched_at": READ_AT_TEXT, "new_pre_excluded_stale_prints": "",
     "new_pre_excluded_spikes": "", "new_pre_filter_status": "params_unavailable",
     "new_pre_filter_params": UNAVAILABLE_PARAMS,
     "changed": "true", "status": "recomputed", "bars_rows": "330", "written": "false"},
    {"ticker": "SPY", "session_date": "2026-10-06", "row_key": "2026-10-06", **OLD,
     "new_pre_high": "100.5", "new_pre_low": "99.5", "new_pre_vwap": "100.0",
     "new_pre_volume": "330000", "new_gap_pct": "1.0101", "new_pre_range_atr": "0.5",
     "new_pre_fetched_at": READ_AT_TEXT, "new_pre_excluded_stale_prints": "0",
     "new_pre_excluded_spikes": "0", "new_pre_filter_status": "ok",
     "new_pre_filter_params": OK_PARAMS,
     "changed": "true", "status": "recomputed", "bars_rows": "330", "written": "false"},
]


def test_the_dry_run_report_equals_the_expected_table(premarket_run, tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        code, _reader = premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY QQQ")

    assert code == 1  # the two QQQ rows were refused
    table, summary = premarket_report(tmp_path)
    assert len(table) == 4
    for got, expected in zip(table, EXPECTED_TABLE):
        sha = got.pop("bars_sha256")
        expected = dict(expected)
        expected_sha = expected.pop("bars_sha256", None)
        assert got == expected
        if expected_sha == "":
            assert sha == ""
        else:
            bars = stored_premarket_bars()[(got["ticker"], date.fromisoformat(got["row_key"]))]
            assert sha == br.bars_basis(bars)["sha256"]

    assert summary["counts"] == {
        "QQQ": {"2026-09-24": {"unproven_rows": 1}, "2026-10-06": {"no_bars": 1}},
        "SPY": {"2026-09-24": {"recomputed": 1}, "2026-10-06": {"recomputed": 1}},
    }
    assert summary["totals"] == {"unproven_rows": 1, "no_bars": 1, "recomputed": 2}
    assert summary["written"] == 0
    assert summary["run_id"] == RUN_ID
    assert summary["arguments"] == {
        "tickers": ["SPY", "QQQ"], "from": "2026-09-24", "to": "2026-10-06", "commit": False}
    assert "RECOMPUTE-PREMARKET SPY 2026-10 candidates=1 changed=1 unchanged=0 refused=0" in caplog.text
    assert "RECOMPUTE-PREMARKET QQQ 2026-09 candidates=1 changed=0 unchanged=0 refused=1" in caplog.text


def test_a_run_that_refuses_no_row_is_exit_zero(premarket_run, tmp_path):
    code, _reader = premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY")
    assert code == 0
    table, _summary = premarket_report(tmp_path)
    assert [r["status"] for r in table] == ["recomputed", "recomputed"]


def test_reads_are_one_a_ticker_and_one_a_month(premarket_run):
    from lib.eastern_time import eastern_bounds_utc

    _code, reader = premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY QQQ")

    (sql, params), = reader.of("pre_filter_params::text")
    text = _collapse(sql)
    assert params == {"tickers": ["SPY", "QQQ"], "first": SEP_24, "last": OCT_6}
    for fragment in (
        "FROM market_data_daily", "ticker = ANY(:tickers)", "date >= :first AND date <= :last",
        "close IS NOT NULL",
        "(pre_high IS NOT NULL OR pre_low IS NOT NULL OR pre_vwap IS NOT NULL "
        "OR gap_pct IS NOT NULL)",
        "pre_filter_params::text AS pre_filter_params", "ORDER BY ticker, date",
    ):
        assert fragment in text, fragment

    daily_reads = reader.of('AS "Open"')
    assert sorted(p["ticker"] for _s, p in daily_reads) == ["QQQ", "SPY"]
    for _sql, p in daily_reads:
        assert p["hi"] == OCT_6
        assert (SEP_24 - p["lo"]).days == 400

    bar_reads = reader.of("FROM market_data_intraday")
    assert sorted((p["t"], p["s0"].date().isoformat()[:7]) for _s, p in bar_reads) == [
        ("QQQ", "2026-09"), ("QQQ", "2026-10"), ("SPY", "2026-09"), ("SPY", "2026-10")]
    for sql, p in bar_reads:
        text = _collapse(sql)
        assert "m.interval = '1min'" in text
        assert "b.inserted_at" in text
        assert text.count("(:s") == 1  # one window a selected session
        day = OCT_6 if p["s0"].month == 10 else SEP_24
        assert (p["s0"], p["e0"]) == eastern_bounds_utc(day, time(4), time(9, 30))

    # The parameters: once a distinct session date, for the run's tickers.
    level_reads = [q for q in premarket_run.params_db.queries]
    assert len(level_reads) == 2


def test_two_sessions_of_a_month_are_one_read_with_two_windows(premarket_run, tmp_path):
    oct_7 = date(2026, 10, 7)
    selected = [stored_row("SPY", OCT_6), stored_row("SPY", oct_7)]
    bars = {("SPY", OCT_6): premarket_bars(OCT_6, inserted="2026-10-07"),
            ("SPY", oct_7): premarket_bars(oct_7, inserted="2026-10-08")}
    reader = premarket_reader(selected=selected, bars=bars)
    # daily history must reach the later session
    reader.answers[2] = ('AS "Open"', lambda _sql, p: daily_history(oct_7, 40))
    code, reader = premarket_run("--recompute-premarket", "--from", "2026-10-06",
                                 "--to", "2026-10-07", "--tickers", "SPY", reader=reader)
    assert code == 0
    (sql, params), = reader.of("FROM market_data_intraday")
    assert _collapse(sql).count("(:s") == 2
    assert {"s0", "e0", "s1", "e1", "t"} == set(params)
    table, _summary = premarket_report(tmp_path)
    assert [r["bars_rows"] for r in table] == ["330", "330"]


def test_the_mode_touches_no_vendor(premarket_run, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a vendor path was reached")

    monkeypatch.setattr(fmd, "process_ticker", forbidden)
    monkeypatch.setattr(fmd, "fetch_and_upsert_vix", forbidden)
    monkeypatch.setattr(fmd, "_run_backfill", forbidden)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "not-read")

    code, _reader = premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY",
                                  record_environ=True)

    assert code == 0
    asked = premarket_run.environ.asked
    assert "ALPHA_VANTAGE_API_KEY" not in asked
    assert "CLOUD_RUN_EXECUTION" in asked  # the mapping was the one the run read


REFUSED = {
    "another ticker": ("--recompute-premarket", *WINDOW, "--tickers", "SPY AMD"),
    "a comma in --tickers": ("--recompute-premarket", *WINDOW, "--tickers", "SPY,QQQ"),
    "no --from": ("--recompute-premarket", "--to", "2026-10-06"),
    "no --to": ("--recompute-premarket", "--from", "2026-09-24"),
    "--from after --to": ("--recompute-premarket", "--from", "2026-10-07", "--to", "2026-10-06"),
    "--to today": ("--recompute-premarket", "--from", "2026-09-24", "--to", "2026-11-14"),
    "--to after today": ("--recompute-premarket", "--from", "2026-09-24", "--to", "2026-11-16"),
    "a malformed date": ("--recompute-premarket", "--from", "2026-5-1x", "--to", "2026-10-06"),
    "with --date": ("--recompute-premarket", *WINDOW, "--date", "2026-10-06"),
    "with --backfill": ("--recompute-premarket", *WINDOW, "--backfill"),
    "with --revert-run": ("--recompute-premarket", *WINDOW, "--revert-run", "x"),
    "--commit alone": ("--commit",),
    "--from alone": ("--from", "2026-09-24"),
    "--report-dir alone": (),
    "--revert-run with a window": ("--revert-run", "x", *WINDOW),
    "--revert-run with --tickers": ("--revert-run", "x", "--tickers", "SPY"),
    "--revert-run with --date": ("--revert-run", "x", "--date", "2026-10-06"),
}


@pytest.mark.parametrize("argv", list(REFUSED.values()), ids=list(REFUSED))
def test_refused_before_any_query(premarket_run, caplog, argv):
    def no_query(_sql, _params):
        raise AssertionError("a query ran before the refusal")

    reader = Reader([("", no_query)])
    with caplog.at_level(logging.ERROR):
        code, reader = premarket_run(*argv, reader=reader)
    assert code == 2
    assert reader.calls == []
    assert premarket_run.params_db.queries == []
    refusals = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(refusals) == 1
    assert "\n" not in refusals[0].getMessage()


def test_no_report_destination_is_refused(premarket_run):
    reader = Reader([])
    code, reader = premarket_run("--recompute-premarket", *WINDOW, reader=reader,
                                 report_dir=False)
    assert code == 2
    assert reader.calls == []


def test_tickers_all_covers_the_three(premarket_run):
    _code, reader = premarket_run("--recompute-premarket", *WINDOW, "--tickers", "ALL")
    (_sql, params), = reader.of("pre_filter_params::text")
    assert params["tickers"] == ["SPY", "QQQ", "IWM"]
    _code, reader = premarket_run("--recompute-premarket", *WINDOW)
    (_sql, params), = reader.of("pre_filter_params::text")
    assert params["tickers"] == ["SPY", "QQQ", "IWM"]


def test_a_session_with_no_prior_daily_row_is_daily_incomplete(premarket_run, tmp_path):
    reader = premarket_reader(history_sessions=1)  # the session's own row and none before it
    code, _reader = premarket_run("--recompute-premarket", "--from", "2026-10-06",
                                  "--to", "2026-10-06", "--tickers", "SPY", reader=reader)
    assert code == 1
    table, summary = premarket_report(tmp_path)
    assert [r["status"] for r in table] == ["daily_incomplete"]
    assert table[0]["new_pre_high"] == "" and table[0]["changed"] == ""
    assert summary["totals"] == {"daily_incomplete": 1}


def test_a_daily_frame_that_stops_before_the_session_is_daily_incomplete(premarket_run,
                                                                           tmp_path):
    reader = premarket_reader()
    reader.answers[2] = ('AS "Open"', lambda _sql, p: daily_history(date(2026, 10, 5), 40))
    code, _reader = premarket_run("--recompute-premarket", "--from", "2026-10-06",
                                  "--to", "2026-10-06", "--tickers", "SPY", reader=reader)
    assert code == 1
    table, _summary = premarket_report(tmp_path)
    assert [r["status"] for r in table] == ["daily_incomplete"]


def test_a_missing_ledger_or_marker_is_exit_two(premarket_run, monkeypatch, caplog):
    monkeypatch.setattr(br, "schema_missing", lambda: ["market_data_daily.pre_recompute_run"])
    reader = Reader([])
    with caplog.at_level(logging.ERROR):
        code, reader = premarket_run("--recompute-premarket", *WINDOW, reader=reader)
        assert code == 2
        code, reader = premarket_run("--recompute-premarket", *WINDOW, "--commit",
                                     reader=reader)
        assert code == 2
    assert reader.calls == []
    assert "market_data_daily.pre_recompute_run" in caplog.text


def test_read_failures_propagate(premarket_run):
    from lib.strat_levels import LevelParamsUnavailable

    for marker, failure in (
        ("pre_recompute_run", ConnectionError("connection refused")),
        ("pre_recompute_run", KeyError("close")),
        ('AS "Open"', ConnectionError("connection refused")),
        ('AS "Open"', KeyError("close")),
        ("FROM market_data_intraday", ConnectionError("connection refused")),
        ("FROM market_data_intraday", KeyError("close")),
    ):
        reader = premarket_reader()

        def fail(_sql, _params, failure=failure):
            raise failure

        reader.answers = [(m, fail if m == marker else a) for m, a in reader.answers]
        with pytest.raises(type(failure)) as caught:
            premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY", reader=reader)
        assert caught.value is failure

    # A failed parameter read is never "write it unfiltered".
    failure = ConnectionError("connection refused")
    broken = ParamsDb()

    def broken_query(_sql, _params=None):
        raise failure

    broken.query = broken_query
    with pytest.raises(LevelParamsUnavailable) as caught:
        premarket_run("--recompute-premarket", *WINDOW, "--tickers", "SPY", params_db=broken)
    assert caught.value.__cause__ is failure


def test_an_unchanged_row_with_a_marker_is_already_current(premarket_run, tmp_path):
    current = stored_row(
        "SPY", OCT_6, pre_high=100.5, pre_low=99.5, pre_vwap=100.0, pre_volume=330000.0,
        gap_pct=1.0101, pre_range_atr=0.5,
        pre_fetched_at=pd.Timestamp("2026-11-13 08:00", tz="UTC"),
        pre_excluded_stale_prints=0.0, pre_excluded_spikes=0.0, pre_filter_status="ok",
        # as the database prints its own jsonb: another key order, same document
        pre_filter_params=json.dumps(json.loads(OK_PARAMS), sort_keys=False),
        pre_recompute_run="an-earlier-run")
    reader = premarket_reader(selected=[current])
    code, _reader = premarket_run("--recompute-premarket", "--from", "2026-10-06",
                                  "--to", "2026-10-06", "--tickers", "SPY", reader=reader)
    assert code == 0
    table, _summary = premarket_report(tmp_path)
    assert [(r["status"], r["changed"]) for r in table] == [("already_current", "false")]

    # The same values with no marker: written once, to record the confirmation.
    reader = premarket_reader(selected=[dict(current, pre_recompute_run=None)])
    code, _reader = premarket_run("--recompute-premarket", "--from", "2026-10-06",
                                  "--to", "2026-10-06", "--tickers", "SPY", reader=reader)
    table, _summary = premarket_report(tmp_path)
    assert [(r["status"], r["changed"]) for r in table] == [("recomputed", "false")]


# ── the modes that were there before ──────────────────────────────────


def test_a_backfill_that_wrote_rows_still_exits_zero(monkeypatch):
    """The module now ends `sys.exit(main())`, and `_run_backfill` returns the
    number of rows it wrote: main() must not hand that count to sys.exit."""
    seen = []

    def backfill(tickers=None, **_kwargs):
        seen.append(tickers)
        return 1500

    monkeypatch.setattr(fmd, "_run_backfill", backfill)
    monkeypatch.setattr(sys, "argv", ["fetch_market_data", "--backfill"])
    assert fmd.main() is None
    monkeypatch.setattr(sys, "argv", ["fetch_market_data", "--backfill", "--tickers", "bf.b"])
    assert fmd.main() is None
    assert seen == [None, ["BF.B"]]


def test_the_module_exits_with_the_code_main_returns():
    source = open(fmd.__file__).read().rstrip().splitlines()
    assert source[-2:] == ["if __name__ == '__main__':", "    sys.exit(main())"]


# ── --revert-run ──────────────────────────────────────────────────────


def test_revert_of_an_unknown_run_is_exit_one(premarket_run, monkeypatch, tmp_path, caplog):
    """An exits run id given to the fetcher: its ledger rows have another
    target, so this entry point finds none."""
    asked = []

    def held_for(run_id, target):
        asked.append((run_id, target))
        return [] if target == br.TARGET_PREMARKET else [{"row_key": "an exits row"}]

    monkeypatch.setattr(br, "ledger_of_run", held_for)
    reader = Reader([("information_schema.columns", schema_ready)])
    with caplog.at_level(logging.ERROR):
        code, reader = premarket_run("--revert-run", "exits-run-A", "--commit", reader=reader)

    assert code == 1
    assert asked == [("exits-run-A", "daily-premarket")]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "exits-run-A" in errors[0] and "daily-premarket" in errors[0]
    assert not (tmp_path / "bar-recompute").exists()


def test_the_bar_read_is_one_index_range_a_window():
    """Each window's bounds are compared to ts inside a lateral subquery the
    planner cannot flatten (OFFSET 0), so the read is one index range a
    window whatever the planner estimates. A plain join to the windows read
    the whole SPY partition on production once a month's sessions were
    listed: 2,536,918 rows for 7,251 returned (db-query-xzdx7, 2026-11-14)."""
    text = _collapse(fmd.premarket_bars_sql(3))
    assert text.count("(:s") == 3
    assert "(VALUES (:s0, :e0), (:s1, :e1), (:s2, :e2)) AS w(start_ts, end_ts)" in text
    assert "CROSS JOIN LATERAL (" in text
    assert "FROM market_data_intraday m" in text
    assert ("WHERE m.ticker = :t AND m.interval = '1min' "
            "AND m.ts >= w.start_ts::timestamptz AND m.ts < w.end_ts::timestamptz "
            "OFFSET 0) AS b") in text
    assert text.startswith(
        "SELECT b.ts, b.open, b.high, b.low, b.close, b.volume, b.inserted_at FROM (VALUES")
    assert text.endswith("ORDER BY b.ts")
