"""Signals router — reads historical signals parquets directly from GCS with TTL caching.

Data source
-----------
gs://adept-mountain-474619-d4-trading-data/raw/data/signals/historical_{ticker}_*_signals.parquet

The parquets are large (hundreds of MB each), so we cache the raw DataFrame per
ticker with a 1h TTL. Filtering (direction, min_score, point-in-time) is then
cheap and happens in-memory on every request.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import gcs_reader  # noqa: E402

log = logging.getLogger(__name__)
router = APIRouter()

GCS_PREFIX = "data/signals/"

# Cache the raw DataFrame per ticker for 1h. Four tickers × one parquet each → 4 entries max.
_DF_CACHE: TTLCache = TTLCache(maxsize=8, ttl=3600)


def _pattern(ticker_lower: str) -> str:
    return rf"^historical_{re.escape(ticker_lower)}_\d{{8}}_\d{{8}}_signals\.parquet$"


def _load_ticker_df(ticker_upper: str) -> tuple[str, pd.DataFrame]:
    """Return (filename, dataframe) for the most recent signals parquet, using cache."""
    if ticker_upper in _DF_CACHE:
        return _DF_CACHE[ticker_upper]

    ticker_lower = ticker_upper.lower()
    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _pattern(ticker_lower))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No signals parquet found in GCS for {ticker_upper}. Run the signals generation pipeline first.",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        # Project to the columns the API actually exposes — drops parquet read
        # time / memory by ~60% on the historical signals files.
        df = gcs_reader.download_parquet(
            blob_name,
            columns=[
                "entry_time",
                "trade_type",
                "entry_price",
                "entry_rsi",
                "entry_ema9",
                "entry_ema20",
                "entry_volume",
                "signal_strength",
                "conditions_met",
                "return_pct",
            ],
        )
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download signals parquet from GCS: {exc}")

    _DF_CACHE[ticker_upper] = (filename, df)
    return filename, df


@router.get("/api/signals/{ticker}")
async def get_signals(
    ticker: str,
    limit: int = Query(default=5000, le=50000),
    direction: str = Query(default="", description="CALL or PUT filter"),
    min_score: int = Query(default=0, ge=0),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD cutoff; returns signals at or before this date"),
    end_time: Optional[str] = Query(default=None, description="HH:MM (24h ET); combined with end_date for minute-precision cutoff"),
):
    """Return historical signals for a ticker from GCS signals parquet.

    Supports point-in-time review via `end_date` (+ optional `end_time`).
    Cutoff semantics: signals where `entry_time <= cutoff` are included.
    """
    ticker_upper = ticker.upper()
    filename, df = _load_ticker_df(ticker_upper)

    # Copy so filters don't mutate the cached frame
    df = df.copy()

    # Point-in-time filter on entry_time (datetime64 column)
    if end_date:
        try:
            cutoff_str = f"{end_date} {end_time}:00" if end_time else f"{end_date} 23:59:59"
            cutoff_ts = pd.Timestamp(cutoff_str)
            if "entry_time" in df.columns:
                df = df[df["entry_time"] <= cutoff_ts]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time: {e}")

    # Rename columns to match frontend expectations
    rename_map = {
        "entry_time": "time",
        "trade_type": "direction",
        "entry_price": "close",
        "entry_rsi": "rsi",
        "entry_ema9": "ema9",
        "entry_ema20": "ema20",
        "entry_volume": "volume",
        "signal_strength": "score",
        "conditions_met": "conditions_met",
        "return_pct": "return_pct",
    }

    available_cols = {k: v for k, v in rename_map.items() if k in df.columns}
    out = df.rename(columns=available_cols)[list(available_cols.values())].copy()

    # Normalize direction to CALL/PUT
    if "direction" in out.columns:
        out["direction"] = out["direction"].str.upper()

    # Add ticker column
    out["ticker"] = ticker_upper

    # Filters
    if direction in ("CALL", "PUT") and "direction" in out.columns:
        out = out[out["direction"] == direction]
    if min_score > 0 and "score" in out.columns:
        out = out[out["score"] >= min_score]

    total_count = len(out)
    out = out.tail(limit)  # most recent N

    # Convert timestamps to strings
    for col in out.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        out[col] = out[col].astype(str)
    if "time" in out.columns:
        out["time"] = out["time"].astype(str)

    # Replace NaN with None
    records = out.where(pd.notnull(out), other=None).to_dict(orient="records")

    return {
        "ticker": ticker_upper,
        "count": total_count,
        "returned": len(records),
        "file": filename,
        "signals": records,
    }
