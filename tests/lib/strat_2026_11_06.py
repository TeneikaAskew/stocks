"""Shared 2026-11-06 session inputs for the FEAT-STRAT-001 tests.

Daily bars: tests/fixtures/strat_levels_2026-11-06_daily.json (Alpha Vantage
TIME_SERIES_DAILY, unadjusted). Premarket bars:
tests/fixtures/premarket_2026-11-06/{QQQ,SPY,IWM}.csv (Alpha Vantage
TIME_SERIES_INTRADAY 1min, extended hours, 04:00 to 09:29 ET).
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DAILY_JSON = FIXTURES / "strat_levels_2026-11-06_daily.json"
PREMARKET_DIR = FIXTURES / "premarket_2026-11-06"
SESSION = date(2026, 11, 6)
PRIOR = date(2026, 11, 5)


@lru_cache(maxsize=None)
def _raw():
    return json.loads(DAILY_JSON.read_text())


def daily(ticker: str, through: date | None = PRIOR) -> pd.DataFrame:
    """Daily bars for `ticker` on a DatetimeIndex named Time, with a Time
    column (the DataLoader shape), through `through` inclusive."""
    raw = _raw()
    rows = raw["tickers"][ticker]
    df = pd.DataFrame(rows, columns=raw["columns"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    })
    df.index.name = "Time"
    if through is not None:
        df = df[df.index <= pd.Timestamp(through)]
    df["Time"] = df.index
    return df.astype({"Open": float, "High": float, "Low": float, "Close": float})


def wilder_atr(df: pd.DataFrame) -> pd.Series:
    """Production ATR(14) (lib.indicators.calculate_atr, Wilder)."""
    from lib.indicators import calculate_atr
    return calculate_atr(df["High"], df["Low"], df["Close"], 14)


def prior_atr(ticker: str) -> float:
    """ATR(14) of the last completed session before 2026-11-06."""
    return float(wilder_atr(daily(ticker)).iloc[-1])


def premarket_bars(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(PREMARKET_DIR / f"{ticker}.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def premarket_context(ticker: str, *, atr14: float | None = "prior", raw: bool = False,
                      params=None) -> dict:
    """calculate_premarket_context on the session's committed bars, with
    the prior session's close and ATR(14) and the ticker's pm_stale_print_atr
    and pm_spike_atr from `params` (default: fixture_params at the #1753
    values). raw=True passes no ATR and no thresholds (no filter)."""
    from lib.indicators import calculate_premarket_context
    from tests.lib.level_params_fixtures import fixture_params
    bars = premarket_bars(ticker)
    d = daily(ticker)
    lp = params if params is not None else fixture_params(ticker, SESSION)
    atr = None if raw else (prior_atr(ticker) if atr14 == "prior" else atr14)

    def threshold(key):
        return None if raw or not lp.ok(key) else lp.value(key)

    return calculate_premarket_context(
        times=bars["timestamp"], open_=bars["open"], high=bars["high"],
        low=bars["low"], close=bars["close"], volume=bars["volume"],
        prev_close=float(d["Close"].iloc[-1]), atr=atr,
        prev_open=float(d["Open"].iloc[-1]),
        stale_print_atr=threshold("pm_stale_print_atr"),
        spike_atr=threshold("pm_spike_atr"),
    )


def session_premarket(ticker: str) -> dict:
    pm = premarket_context(ticker)
    return {"date": SESSION.isoformat(), "pre_high": pm["pre_high"],
            "pre_low": pm["pre_low"], "pre_vwap": pm["pre_vwap"],
            "gap_pct": pm["gap_pct"],
            "pre_filter_status": "ok" if pm["filtered"] else "atr_unavailable"}


def loader_frame(ticker: str) -> pd.DataFrame:
    """What DataLoader.load_daily returns at 08:30 ET on 2026-11-06: bars
    through 2026-11-05 with ATR14, plus the session's own row carrying only
    the premarket columns written by fetch-premarket-refresh at 08:20 ET."""
    from lib.indicators import calculate_atr
    df = daily(ticker).copy()
    df["ATR14"] = wilder_atr(df)
    df["ATR5"] = calculate_atr(df["High"], df["Low"], df["Close"], 5)
    for col in ("pre_high", "pre_low", "pre_vwap", "gap_pct"):
        df[col] = float("nan")
    df["pre_filter_status"] = None
    snap = session_premarket(ticker)
    row = pd.DataFrame(
        {"Open": [float("nan")], "High": [float("nan")], "Low": [float("nan")],
         "Close": [float("nan")], "Volume": [float("nan")], "ATR14": [float("nan")],
         "ATR5": [float("nan")],
         "pre_high": [snap["pre_high"]], "pre_low": [snap["pre_low"]],
         "pre_vwap": [snap["pre_vwap"]], "gap_pct": [snap["gap_pct"]],
         "pre_filter_status": [snap["pre_filter_status"]]},
        index=pd.DatetimeIndex([pd.Timestamp(SESSION)], name="Time"),
    )
    row["Time"] = row.index
    return pd.concat([df, row])


def run_brief(monkeypatch, ticker: str, frame: pd.DataFrame, as_of: str = "2026-11-06",
              *, params_db=None) -> dict:
    """Drive gcp.premarket_brief.generate_premarket_brief (the production
    playbook path) offline on `frame` and return the ticker's entry. The
    level parameters come from `params_db` (a level_params_fixtures.ParamsDb)
    through load_level_params's own SQL; by default every key at the #1753
    values."""
    from tests.lib.level_params_fixtures import legacy_db
    import socket

    import gcp.database as database
    from gcp import premarket_brief as pb
    from lib.config import AppConfig
    from lib.data_loader import DataLoader

    def refuse(*_a, **_k):
        raise AssertionError("external I/O attempted in an offline brief run")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: False)
    cfg = AppConfig()
    cfg.market.tickers = [ticker]
    for key, value in {"BRIEF_AS_OF": as_of, "BRIEF_AMC_REACTIONS": "0",
                       "BRIEF_LLM_DISABLE": "1", "BRIEF_TICKERS": ticker}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(DataLoader, "load_daily", lambda *a, **k: frame.copy())
    monkeypatch.setattr(pb, "check_call_conditions", lambda row: (4, []))
    monkeypatch.setattr(pb, "check_put_conditions", lambda row: (3, []))
    monkeypatch.setattr(pb, "load_earnings_for_brief", lambda *a, **k: {"earnings": []})
    monkeypatch.setattr(pb, "_ew_recap_or_unavailable", lambda *a, **k: {})
    monkeypatch.setattr(pb, "load_economic_events", lambda *a, **k: {"today": []})
    monkeypatch.setattr(pb, "_load_gamma_freshness", lambda *a, **k: dict(
        data_source="unavailable", snapshot_ts=None, snapshot_date=None, days_behind=None))
    monkeypatch.setattr(pb, "_delete_null_close_rows", lambda *a: None)
    db = params_db if params_db is not None else legacy_db(ticker)
    monkeypatch.setattr(pb, "_level_params_query", db.query)

    persisted = []

    class _Conn:
        class connection:  # noqa: N801
            @staticmethod
            def commit():
                return None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    import lib.strat_levels as sl
    monkeypatch.setattr(database, "get_engine", lambda: _Engine())
    monkeypatch.setattr(sl, "persist_level_map",
                        lambda level_map, conn, **k: persisted.append(level_map) or len(level_map.levels))
    brief = pb.generate_premarket_brief(cfg=cfg)
    out = brief["tickers"][ticker]
    out["_persisted_level_maps"] = persisted
    return out


def run_planner(monkeypatch, ticker: str, frame: pd.DataFrame, direction: str,
                *, live_basis: dict | None = None, conviction: str = "medium",
                params_db=None):
    """The planner's production path: summarize_session_levels (through
    summarizers._query for the session premarket row and the live
    level_basis, and summarizers._query_strict for the level parameters)
    into a bundle, then context_from_bundle and compute_persona_plans.
    Returns (bundle_section, ctx, plans)."""
    from lib.agents import summarizers
    from lib.agents.trade_planner import compute_persona_plans, context_from_bundle
    from tests.lib.level_params_fixtures import legacy_db

    db = params_db if params_db is not None else legacy_db(ticker)

    snap = premarket_snapshot_row(frame)

    def fake_query(sql, params=None):
        if "level_basis" in sql:
            if live_basis is None:
                return pd.DataFrame()
            return pd.DataFrame([{"ticker": ticker, "level_basis": json.dumps(live_basis)}])
        if "pre_high" in sql and "market_data_daily" in sql:
            return snap
        return pd.DataFrame()

    class _Loader:
        calls = 0

        def load_daily(self, *_a, **_k):
            _Loader.calls += 1
            return frame.copy()

    monkeypatch.setattr(summarizers, "_query", fake_query)
    monkeypatch.setattr(summarizers, "_query_strict", db.query)
    section = summarizers.summarize_session_levels(ticker, as_of=SESSION, loader=_Loader())
    d = daily(ticker)
    bundle = {
        "ticker": ticker,
        "market": {"close": float(d["Close"].iloc[-1]),
                   "atr_14": float(wilder_atr(d).iloc[-1])},
        "strat": {"ftfc_score": 0.8 if direction == "long" else -0.8},
        "session_levels": section,
    }
    ctx = context_from_bundle(bundle, direction, conviction)
    return section, ctx, compute_persona_plans(ctx), _Loader.calls


def premarket_snapshot_row(frame: pd.DataFrame) -> pd.DataFrame:
    """The market_data_daily row dated the session, as summarizers._query
    returns it (empty when the session row is absent)."""
    idx = frame.index
    rows = frame[idx.normalize() == pd.Timestamp(SESSION)]
    if rows.empty or "pre_high" not in rows.columns:
        return pd.DataFrame()
    r = rows.iloc[-1]
    return pd.DataFrame([{"date": SESSION, "pre_high": r.get("pre_high"),
                          "pre_low": r.get("pre_low"), "pre_vwap": r.get("pre_vwap"),
                          "gap_pct": r.get("gap_pct"),
                          "pre_filter_status": r.get("pre_filter_status")}])
