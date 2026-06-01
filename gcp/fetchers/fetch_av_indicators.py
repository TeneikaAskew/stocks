#!/usr/bin/env python3
"""Phase-2 fetcher — AlphaVantage pre-computed indicators.

Lands into market_data_indicators. SCAFFOLD ONLY — backfill not yet
executed. Magnitude Engine Phase 2 will be marked PENDING_BACKFILL in
the results doc until this fetcher's backfill mode has run successfully
and rows for the IWM/SPY/QQQ × daily + 15min coverage exist.

Why a separate fetcher rather than extending fetch_market_data.py:
fetch_market_data.py computes indicators LOCALLY from OHLCV via
lib.indicators. We INTENTIONALLY pull AV's pre-computed versions for
Phase 2 — per spec ("If AV is missing an indicator we want, do NOT
compute a substitute and call it the same thing"). Co-mingling local
and AV indicators in one fetcher creates exactly that substitution
risk.

AV functions used:
  ADX, MFI, ADOSC, AROON, ROC, BBANDS

API: 75 req/min premium. Each function call returns the full history
for one (ticker, interval, function). 3 tickers × 2 intervals (daily,
15min) × 6 functions = 36 calls per backfill — ~30 seconds at 75 RPM.

Usage:
    python -m gcp.fetchers.fetch_av_indicators --ticker SPY --intervals daily,15min
    python -m gcp.fetchers.fetch_av_indicators --all --intervals daily,15min

NOT scheduled. Run manually to backfill before dispatching magnitude
engine phase 2 walk-forward.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine, upsert_dataframe
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
SYMBOLS_DEFAULT = ["SPY", "IWM", "QQQ"]
INTERVALS_DEFAULT = ["daily", "15min"]

# (function, kwargs) per indicator.  series_type=close everywhere we accept it.
INDICATOR_FUNCTIONS: dict[str, dict[str, Any]] = {
    "ADX":    {"function": "ADX",    "time_period": 14},
    "MFI":    {"function": "MFI",    "time_period": 14},
    "ADOSC":  {"function": "ADOSC",  "fastperiod": 3, "slowperiod": 10},
    "AROON":  {"function": "AROON",  "time_period": 14},
    "ROC":    {"function": "ROC",    "time_period": 10, "series_type": "close"},
    "BBANDS": {"function": "BBANDS", "time_period": 20, "series_type": "close",
                "nbdevup": 2, "nbdevdn": 2},
}

# Column rename per function.  AV's "Technical Analysis: X" payloads use
# numeric strings per timestamp; we normalize into our schema names.
COL_MAP: dict[str, dict[str, str]] = {
    "ADX":    {"ADX": "av_adx"},
    "MFI":    {"MFI": "av_mfi"},
    "ADOSC":  {"Chaikin A/D": "av_chaikin_ad_osc"},
    "AROON":  {"Aroon Up": "av_aroon_up", "Aroon Down": "av_aroon_down"},
    "ROC":    {"ROC": "av_roc"},
    "BBANDS": {
        "Real Upper Band":  "av_bbands_upper",
        "Real Middle Band": "av_bbands_middle",
        "Real Lower Band":  "av_bbands_lower",
    },
}


def _av_call(api_key: str, params: dict) -> dict:
    """Single AV GET. Returns the parsed JSON or raises."""
    params["apikey"] = api_key
    r = requests.get(AV_BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    if "Note" in j or "Information" in j:
        raise RuntimeError(f"AV rate-limit or note: {j.get('Note') or j.get('Information')}")
    if "Error Message" in j:
        raise RuntimeError(f"AV error: {j['Error Message']}")
    return j


def fetch_indicator(symbol: str, interval: str, indicator: str, api_key: str) -> pd.DataFrame:
    """Fetch one (symbol, interval, indicator) full history from AV."""
    params = INDICATOR_FUNCTIONS[indicator].copy()
    params["symbol"] = symbol
    params["interval"] = interval  # AV uses 'daily' or '15min'
    j = _av_call(api_key, params)

    # AV returns "Technical Analysis: <function name>" — find the right key.
    payload_key = next((k for k in j.keys() if k.startswith("Technical Analysis")), None)
    if not payload_key:
        log.warning("no payload key in AV response for %s %s %s",
                    symbol, interval, indicator)
        return pd.DataFrame()
    rows = []
    rename = COL_MAP[indicator]
    for ts_str, vals in j[payload_key].items():
        row: dict[str, Any] = {"ts": ts_str}
        for av_col, our_col in rename.items():
            v = vals.get(av_col)
            row[our_col] = float(v) if v not in (None, "", "NaN") else None
        rows.append(row)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["ticker"] = symbol
    df["interval"] = interval
    return df


def merge_indicator_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Outer-merge per-indicator frames on (ticker, interval, ts).
    Different indicators may have slightly different histories; outer
    keeps the union and NaN-fills the gaps.

    Per Rule 3.7: NaN fills here are correct — they signal "AV did not
    return a value at this timestamp." Downstream the model sees NaN
    and we (do not) impute with 0.
    """
    if not frames:
        return pd.DataFrame()
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=["ticker", "interval", "ts"], how="outer")
    return out


def compute_bbands_bandwidth(df: pd.DataFrame) -> pd.DataFrame:
    """Derive av_bbands_bandwidth from upper/middle/lower."""
    if {"av_bbands_upper", "av_bbands_middle", "av_bbands_lower"}.issubset(df.columns):
        # bandwidth = (upper - lower) / middle.  NaN-preserving.
        valid = (
            df["av_bbands_middle"].notna() & (df["av_bbands_middle"] != 0)
        )
        df["av_bbands_bandwidth"] = (df["av_bbands_upper"] - df["av_bbands_lower"]) / df["av_bbands_middle"]
        df.loc[~valid, "av_bbands_bandwidth"] = None
    return df


def fetch_and_persist(symbol: str, interval: str, api_key: str, engine) -> int:
    cfg = AlphaVantageConfig()
    interval_sleep = cfg.delay_between_calls
    frames = []
    for ind in INDICATOR_FUNCTIONS:
        log.info("fetching %s %s %s", symbol, interval, ind)
        try:
            f = fetch_indicator(symbol, interval, ind, api_key)
            if not f.empty:
                frames.append(f)
        except Exception as e:
            # Per Rule 3.7: explicit failure surfaced; the row will be
            # missing for this (symbol, interval, indicator) — downstream
            # walk-forward will see NaN for that column.  We do NOT fill.
            log.error("fetch %s/%s/%s failed: %s", symbol, interval, ind, e)
        time.sleep(interval_sleep)
    merged = merge_indicator_frames(frames)
    if merged.empty:
        return 0
    merged = compute_bbands_bandwidth(merged)
    n = len(merged)
    upsert_dataframe(
        merged,
        table="market_data_indicators",
        conflict_cols=["ticker", "interval", "ts"],
    )
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--intervals", default=",".join(INTERVALS_DEFAULT))
    args = p.parse_args()

    keys = [os.environ.get("ALPHA_VANTAGE_API_KEY", "")]
    if not any(keys):
        raise SystemExit("ALPHA_VANTAGE_API_KEY not set")
    api_key = keys[0]

    symbols = SYMBOLS_DEFAULT if args.all else [args.ticker]
    if not symbols or not symbols[0]:
        raise SystemExit("Specify --ticker or --all")
    intervals = [i.strip() for i in args.intervals.split(",")]

    engine = get_engine()
    total = 0
    for s in symbols:
        for itv in intervals:
            total += fetch_and_persist(s, itv, api_key, engine)
    log.info("DONE — wrote %d rows", total)


if __name__ == "__main__":
    main()
