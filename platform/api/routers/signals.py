"""Signals router — reads historical signals parquets from data/signals/"""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import pandas as pd

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIGNALS_DIR = PROJECT_ROOT / "data" / "signals"


def _find_signals_file(ticker: str) -> Path | None:
    """Find the most recent signals parquet for a ticker."""
    ticker_lower = ticker.lower()
    files = sorted(
        SIGNALS_DIR.glob(f"historical_{ticker_lower}_*_signals.parquet"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


@router.get("/api/signals/{ticker}")
async def get_signals(
    ticker: str,
    limit: int = Query(default=5000, le=50000),
    direction: str = Query(default="", description="CALL or PUT filter"),
    min_score: int = Query(default=0, ge=0),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD cutoff; returns signals at or before this date"),
    end_time: Optional[str] = Query(default=None, description="HH:MM (24h ET); combined with end_date for minute-precision cutoff"),
):
    """Return historical signals for a ticker from the signals parquet.

    Supports point-in-time review via `end_date` (+ optional `end_time`).
    Cutoff semantics: signals where `entry_time <= cutoff` are included.
    """
    ticker_upper = ticker.upper()
    path = _find_signals_file(ticker)

    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No signals file found for {ticker_upper}. Run the signals generation pipeline first.",
        )

    try:
        df = pd.read_parquet(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading signals: {e}")

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
        "file": path.name,
        "signals": records,
    }
