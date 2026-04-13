"""
Backtest router — reads directly from GCS with in-memory TTL caching.

Endpoints
---------
GET /api/backtest/results/{ticker}
    Return trades from the most recent backtest CSV for the given ticker.

GET /api/backtest/equity/{ticker}
    Return equity curve from the most recent equity CSV for the given ticker.

GET /api/backtest/all/{ticker}
    List all backtest runs for a ticker, sorted newest first, with summary metrics.

Data source
-----------
All reads come from gs://adept-mountain-474619-d4-trading-data/raw/data/backtest_results/
via `api.gcs_reader`. No local filesystem reads. TTLCache layers keep repeat
requests fast — first request per (ticker, variant) pays the GCS download cost,
subsequent requests in the TTL window are in-memory.

Cache TTLs:
  * `/results/{ticker}`  — 1h (backtest runs rarely; data is immutable once written)
  * `/equity/{ticker}`   — 1h
  * `/all/{ticker}`      — 10m (listing can change as new runs land)
"""
import logging
import re
import sys
from pathlib import Path

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

# Project root so we can import from sibling packages
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the shared GCS reader. The `api` package is platform/api/.
from api import gcs_reader  # noqa: E402

log = logging.getLogger(__name__)
router = APIRouter()

# GCS prefix (relative to the `raw/` BASE_PREFIX in gcs_reader)
GCS_PREFIX = "data/backtest_results/"

# Filename patterns — anchored and escaped
def _backtest_pattern(ticker_upper: str) -> str:
    return rf"^backtest_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"

def _equity_pattern(ticker_upper: str) -> str:
    return rf"^equity_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"

# ── Caches ──────────────────────────────────────────────────────────────────
_RESULTS_CACHE: TTLCache = TTLCache(maxsize=32, ttl=3600)   # 1h
_EQUITY_CACHE: TTLCache = TTLCache(maxsize=32, ttl=3600)    # 1h
_ALL_RUNS_CACHE: TTLCache = TTLCache(maxsize=16, ttl=600)   # 10m


# ── Helpers ─────────────────────────────────────────────────────────────────

def _timestamp_from_name(basename: str) -> str:
    """Extract YYYYMMDD_HHMMSS from backtest_TICKER_YYYYMMDD_HHMMSS.csv."""
    stem = basename.rsplit(".", 1)[0]  # drop .csv
    parts = stem.split("_")
    return "_".join(parts[2:]) if len(parts) >= 4 else ""


def _dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list[dict], replacing NaN with None and numerics → float."""
    df = df.where(pd.notna(df), other=None)
    for col in df.select_dtypes(include="number").columns:
        df[col] = df[col].apply(lambda x: float(x) if x is not None else None)
    return df.to_dict(orient="records")


def _summarize_returns(df: pd.DataFrame) -> dict:
    summary: dict = {}
    if "return_pct" not in df.columns:
        return summary
    returns = df["return_pct"].dropna().astype(float)
    if len(returns) == 0:
        return summary
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    summary = {
        "total_trades": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(returns), 4),
        "avg_return_pct": round(returns.mean(), 4),
        "avg_win_pct": round(wins.mean(), 4) if len(wins) else None,
        "avg_loss_pct": round(losses.mean(), 4) if len(losses) else None,
        "total_return_pct": round(returns.sum(), 4),
    }
    return summary


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/api/backtest/results/{ticker}")
async def get_backtest_results(ticker: str):
    """Return trades from the most recent backtest CSV for the given ticker."""
    ticker_upper = ticker.upper()

    if ticker_upper in _RESULTS_CACHE:
        return _RESULTS_CACHE[ticker_upper]

    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _backtest_pattern(ticker_upper))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest results found in GCS for ticker '{ticker_upper}'",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        df = gcs_reader.download_csv(blob_name)
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download backtest CSV from GCS: {exc}")

    if df.empty:
        resp = {
            "ticker": ticker_upper,
            "filename": filename,
            "trade_count": 0,
            "summary": {},
            "trades": [],
        }
        _RESULTS_CACHE[ticker_upper] = resp
        return resp

    summary = _summarize_returns(df)
    trades = _dataframe_to_records(df)
    resp = {
        "ticker": ticker_upper,
        "filename": filename,
        "trade_count": len(trades),
        "summary": summary,
        "trades": trades,
    }
    _RESULTS_CACHE[ticker_upper] = resp
    return resp


@router.get("/api/backtest/equity/{ticker}")
async def get_equity_curve(ticker: str):
    """Return equity curve from the most recent equity CSV for the given ticker."""
    ticker_upper = ticker.upper()

    if ticker_upper in _EQUITY_CACHE:
        return _EQUITY_CACHE[ticker_upper]

    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _equity_pattern(ticker_upper))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No equity curve found in GCS for ticker '{ticker_upper}'",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        df = gcs_reader.download_csv(blob_name)
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download equity CSV from GCS: {exc}")

    if df.empty:
        resp = {"ticker": ticker_upper, "filename": filename, "summary": {}, "dates": [], "values": []}
        _EQUITY_CACHE[ticker_upper] = resp
        return resp

    # Equity CSVs have: "Unnamed: 0" (date index) and "0" (equity value)
    date_col = None
    value_col = None
    for col in df.columns:
        if col in ("Unnamed: 0", "date", "Date", "index"):
            date_col = col
        elif col in ("0", "equity", "Equity", "value", "Value"):
            value_col = col

    # Fallback: first col = date, second col = value
    if date_col is None and len(df.columns) >= 1:
        date_col = df.columns[0]
    if value_col is None and len(df.columns) >= 2:
        value_col = df.columns[1]

    dates = df[date_col].astype(str).tolist() if date_col else []
    values = [float(v) if pd.notna(v) else None for v in df[value_col]] if value_col else []

    # Summary stats
    clean_values = [v for v in values if v is not None]
    summary: dict = {}
    if clean_values:
        start_val = clean_values[0]
        end_val = clean_values[-1]
        peak = max(clean_values)
        trough_after_peak = min(clean_values[clean_values.index(peak):])
        max_drawdown = (trough_after_peak - peak) / peak if peak != 0 else 0.0
        total_return = (end_val - start_val) / start_val if start_val != 0 else 0.0
        summary = {
            "start_value": round(start_val, 4),
            "end_value": round(end_val, 4),
            "peak_value": round(peak, 4),
            "total_return_pct": round(total_return * 100, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4),
            "data_points": len(clean_values),
        }

    resp = {
        "ticker": ticker_upper,
        "filename": filename,
        "summary": summary,
        "dates": dates,
        "values": values,
    }
    _EQUITY_CACHE[ticker_upper] = resp
    return resp


@router.get("/api/backtest/all/{ticker}")
async def list_all_backtests(ticker: str):
    """List all backtest runs for a ticker, sorted by timestamp descending."""
    ticker_upper = ticker.upper()

    if ticker_upper in _ALL_RUNS_CACHE:
        return _ALL_RUNS_CACHE[ticker_upper]

    backtest_blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _backtest_pattern(ticker_upper))
    if not backtest_blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest files found in GCS for ticker '{ticker_upper}'",
        )

    # Pre-fetch equity blob list so we can check existence without another LIST call per file
    equity_blobs = set(gcs_reader.list_matching_blobs(GCS_PREFIX, _equity_pattern(ticker_upper)))

    runs = []
    for blob_name in backtest_blobs:
        filename = blob_name.rsplit("/", 1)[-1]
        timestamp = _timestamp_from_name(filename)

        info = {
            "filename": filename,
            "path": f"gs://{gcs_reader.BUCKET}/{blob_name}",
            "timestamp": timestamp,
            # modified/size_bytes are not available without extra metadata fetches;
            # frontend doesn't use them as sort keys since we already sort by timestamp
            "modified": None,
            "size_bytes": None,
            "row_count": None,
        }

        # Does an equity curve exist for this run?
        equity_blob = f"{gcs_reader.BASE_PREFIX}{GCS_PREFIX}equity_{ticker_upper}_{timestamp}.csv"
        info["has_equity_curve"] = equity_blob in equity_blobs

        # Load minimal stats: just return_pct column
        try:
            df = gcs_reader.download_csv(blob_name)
            if "return_pct" in df.columns:
                returns = df["return_pct"].dropna().astype(float)
                wins = returns[returns > 0]
                info["trade_count"] = len(returns)
                info["row_count"] = len(returns)
                info["win_rate"] = round(len(wins) / len(returns), 4) if len(returns) else None
                info["avg_return_pct"] = round(returns.mean(), 4) if len(returns) else None
            else:
                info["trade_count"] = len(df)
                info["row_count"] = len(df)
                info["win_rate"] = None
                info["avg_return_pct"] = None
        except Exception as exc:
            log.warning("Failed to load stats for %s: %s", blob_name, exc)
            info["trade_count"] = None
            info["win_rate"] = None
            info["avg_return_pct"] = None

        runs.append(info)

    resp = {
        "ticker": ticker_upper,
        "total_runs": len(runs),
        "runs": runs,
    }
    _ALL_RUNS_CACHE[ticker_upper] = resp
    return resp
