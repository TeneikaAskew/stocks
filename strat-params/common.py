"""Shared inputs for the FEAT-STRAT-001 #1766 offline calibration, evidence
and replay. Everything reads CSV exports of production tables (read-only
db_query_cr.sh runs); nothing here connects to a database or posts.

daily CSV: the #1753 export (export_daily.sql in ../one-level/prod), columns
as DataLoader.load_daily reads them. minutes CSVs: export_minutes_<t>.sql,
columns ts, open, high, low, close, volume.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

TICKERS = ("SPY", "QQQ", "IWM")
AS_OF = "2026-11-06"


def repo_root() -> Path:
    import lib  # noqa: PLC0415
    return Path(lib.__file__).resolve().parents[1]


def policy_rows() -> list[dict]:
    """The level_param_policy seed exactly as gcp/schema.sql writes it,
    executed in SQLite (the statement is plain INSERT ... ON CONFLICT DO
    NOTHING)."""
    text = (repo_root() / "gcp" / "schema.sql").read_text()
    m = re.search(r"INSERT INTO level_param_policy \(.*?ON CONFLICT \(param_key, effective_from\) DO NOTHING;",
                  text, re.S)
    if not m:
        raise SystemExit("policy seed not found in gcp/schema.sql")
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE level_param_policy (param_key TEXT, method_id TEXT, statistic_q REAL,"
                " lookback_sessions INTEGER, min_sample INTEGER, extra TEXT, effective_from TEXT,"
                " note TEXT, PRIMARY KEY (param_key, effective_from))")
    con.execute(m.group(0))
    df = pd.read_sql("SELECT param_key, method_id, statistic_q, lookback_sessions, min_sample, extra,"
                     " effective_from FROM level_param_policy", con)
    import json  # noqa: PLC0415
    rows = df.to_dict("records")
    for r in rows:
        r["extra"] = json.loads(r["extra"]) if r["extra"] else None
        r["effective_from"] = pd.Timestamp(r["effective_from"]).date()
        for k in ("statistic_q",):
            r[k] = None if pd.isna(r[k]) else float(r[k])
        for k in ("lookback_sessions", "min_sample"):
            r[k] = None if pd.isna(r[k]) else int(r[k])
    return rows


def load_daily_export(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def daily_for_job(export: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """What DAILY_SQL returns: date, open, high, low, close, atr_14, atr_5,
    sma_200. Production has no atr_5 column yet, so it is computed the way
    the nightly writer will compute it (lib.indicators.calculate_atr, 5)."""
    from lib.indicators import calculate_atr  # noqa: PLC0415
    d = export[export["ticker"] == ticker].sort_values("date").reset_index(drop=True)
    out = pd.DataFrame({"date": d["date"], "open": d["Open"], "high": d["High"], "low": d["Low"],
                        "close": d["Close"], "atr_14": d["atr_14"],
                        "sma_200": d["sma_200"] if "sma_200" in d else None})
    out["atr_5"] = calculate_atr(d["High"], d["Low"], d["Close"], 5).to_numpy()
    return out


def load_minutes(path: Path) -> pd.DataFrame:
    m = pd.read_csv(path)
    m["ts"] = pd.to_datetime(m["ts"], utc=True)
    return m.sort_values("ts").reset_index(drop=True)


def make_query(daily: dict, minutes: dict):
    """A query_fn answering the job's DAILY_SQL and MINUTES_SQL from the
    exports. Anything else raises, so no unexpected read is answered."""
    def query(sql, params=None):
        p = params or {}
        t = p.get("ticker")
        if "FROM market_data_daily" in sql:
            d = daily[t]
            start, before = pd.Timestamp(p["start"]).date(), pd.Timestamp(p["before"]).date()
            return d[(d["date"] >= start) & (d["date"] < before)].reset_index(drop=True)
        if "FROM market_data_intraday" in sql:
            m = minutes[t]
            lo, hi = pd.Timestamp(p["start"]), pd.Timestamp(p["end"])
            lo = lo.tz_localize("UTC") if lo.tzinfo is None else lo
            hi = hi.tz_localize("UTC") if hi.tzinfo is None else hi
            return m[(m["ts"] >= lo) & (m["ts"] < hi)].reset_index(drop=True)
        raise RuntimeError(f"unexpected query: {sql[:80]}")
    return query
