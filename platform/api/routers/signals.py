"""Signals router — reads from Cloud SQL ``historical_signals``.

Data source
-----------
Cloud SQL ``historical_signals`` table populated by
``scripts/run_historical_signals.py``. Replaced the previous
``gs://.../data/signals/historical_{ticker}_*_signals.parquet`` path,
which paid a multi-hundred-MB cold-start cost on first request.

Filtering happens server-side in PostgreSQL (indexed on
``ticker, entry_time``) so requests are sub-100ms regardless of how
much history exists.

Falls back to the legacy GCS parquet path when Cloud SQL is not
configured (e.g. local dev without ``CLOUD_SQL_CONNECTION_NAME``).
"""
import logging
import os
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

# ── Cloud SQL availability ─────────────────────────────────────────────────
_CLOUD_SQL = bool(
    os.environ.get('CLOUD_SQL_CONNECTION_NAME')
    and os.environ.get('DB_USER')
    and os.environ.get('DB_PASS')
    and os.environ.get('DB_NAME')
)

# ── Legacy parquet fallback (kept for local-dev without Cloud SQL) ─────────
GCS_PREFIX = "data/signals/"
_DF_CACHE: TTLCache = TTLCache(maxsize=8, ttl=3600)


def _pattern(ticker_lower: str) -> str:
    return rf"^historical_{re.escape(ticker_lower)}_\d{{8}}_\d{{8}}_signals\.parquet$"


def _load_ticker_df_parquet(ticker_upper: str) -> tuple[str, pd.DataFrame]:
    """Legacy path: load from GCS parquet. Used only when Cloud SQL is off."""
    if ticker_upper in _DF_CACHE:
        return _DF_CACHE[ticker_upper]

    ticker_lower = ticker_upper.lower()
    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _pattern(ticker_lower))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No signals parquet found in GCS for {ticker_upper}.",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        df = gcs_reader.download_parquet(
            blob_name,
            columns=[
                "entry_time", "trade_type", "entry_price", "entry_rsi",
                "entry_ema9", "entry_ema20", "entry_volume",
                "signal_strength", "conditions_met", "return_pct",
            ],
        )
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download signals parquet from GCS: {exc}")

    _DF_CACHE[ticker_upper] = (filename, df)
    return filename, df


def _query_signals_sql(
    ticker_upper: str,
    limit: int,
    direction: str,
    min_score: int,
    end_date: Optional[str],
    end_time: Optional[str],
) -> tuple[int, list[dict]]:
    """Cloud SQL query path. Returns (total_count_in_window, rows[<=limit])."""
    from gcp.database import query_to_dataframe  # lazy import

    where = ['ticker = :ticker']
    params: dict = {'ticker': ticker_upper}

    if direction in ('CALL', 'PUT'):
        where.append('UPPER(trade_type) = :direction')
        params['direction'] = direction
    if min_score > 0:
        where.append('signal_strength >= :min_score')
        params['min_score'] = min_score
    if end_date:
        cutoff = f"{end_date} {end_time}:00" if end_time else f"{end_date} 23:59:59"
        where.append('entry_time <= CAST(:cutoff AS timestamptz)')
        params['cutoff'] = cutoff

    where_sql = ' AND '.join(where)

    # Total count first (cheap with the (ticker, entry_time) index)
    count_df = query_to_dataframe(
        f'SELECT COUNT(*) AS n FROM historical_signals WHERE {where_sql}',
        params,
    )
    total = int(count_df.iloc[0]['n']) if not count_df.empty else 0

    if total == 0:
        return (0, [])

    # Most-recent N rows. Fetch ASC so the response order matches the legacy
    # parquet behaviour (`out.tail(limit)` produced ascending entries).
    rows_df = query_to_dataframe(
        f"""
        SELECT * FROM (
            SELECT entry_time AS time,
                   UPPER(trade_type) AS direction,
                   entry_price AS close,
                   entry_rsi AS rsi,
                   entry_ema9 AS ema9,
                   entry_ema20 AS ema20,
                   entry_volume AS volume,
                   signal_strength AS score,
                   conditions_met,
                   return_pct
            FROM historical_signals
            WHERE {where_sql}
            ORDER BY entry_time DESC
            LIMIT :limit
        ) sub
        ORDER BY time ASC
        """,
        {**params, 'limit': limit},
    )

    if 'time' in rows_df.columns:
        rows_df['time'] = rows_df['time'].astype(str)
    rows_df['ticker'] = ticker_upper
    records = rows_df.where(pd.notnull(rows_df), other=None).to_dict(orient='records')
    return (total, records)


@router.get("/api/signals/{ticker}")
async def get_signals(
    ticker: str,
    limit: int = Query(default=5000, le=50000),
    direction: str = Query(default="", description="CALL or PUT filter"),
    min_score: int = Query(default=0, ge=0),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD cutoff"),
    end_time: Optional[str] = Query(default=None, description="HH:MM (24h ET)"),
):
    """Return historical signals for a ticker.

    Reads from Cloud SQL ``historical_signals`` when configured, falls back
    to the legacy GCS parquet otherwise. Supports point-in-time review via
    ``end_date`` (+ optional ``end_time``).
    """
    ticker_upper = ticker.upper()

    if _CLOUD_SQL:
        try:
            total, records = _query_signals_sql(
                ticker_upper, limit, direction, min_score, end_date, end_time
            )
            return {
                "ticker": ticker_upper,
                "count": total,
                "returned": len(records),
                "source": "cloud_sql",
                "signals": records,
            }
        except HTTPException:
            raise
        except Exception as exc:
            log.warning("Cloud SQL signals query failed (%s) — falling back to parquet", exc)

    # ── Fallback: legacy GCS parquet path ────────────────────────────────
    filename, df = _load_ticker_df_parquet(ticker_upper)
    df = df.copy()

    if end_date:
        try:
            cutoff_str = f"{end_date} {end_time}:00" if end_time else f"{end_date} 23:59:59"
            cutoff_ts = pd.Timestamp(cutoff_str)
            if "entry_time" in df.columns:
                df = df[df["entry_time"] <= cutoff_ts]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time: {e}")

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

    if "direction" in out.columns:
        out["direction"] = out["direction"].str.upper()

    out["ticker"] = ticker_upper

    if direction in ("CALL", "PUT") and "direction" in out.columns:
        out = out[out["direction"] == direction]
    if min_score > 0 and "score" in out.columns:
        out = out[out["score"] >= min_score]

    total_count = len(out)
    out = out.tail(limit)

    for col in out.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        out[col] = out[col].astype(str)
    if "time" in out.columns:
        out["time"] = out["time"].astype(str)

    records = out.where(pd.notnull(out), other=None).to_dict(orient="records")

    return {
        "ticker": ticker_upper,
        "count": total_count,
        "returned": len(records),
        "source": "gcs_parquet",
        "file": filename,
        "signals": records,
    }


# ── /similar — "like-this-bar" historical setup lookup ─────────────────────
# Powers the Charts page "Similar Setups" card. Given the conditions of a
# specific bar (or the latest live bar), find historical signals where the
# strategy fired with a similar score + RSI band + direction, and surface
# stats: count, median MFE, win rate, recent matches.
#
# Cloud SQL only — the parquet path doesn't have indexes for this kind of
# bucket query, so when CLOUD_SQL_CONNECTION_NAME is unset this returns
# 404 rather than degrading silently.

@router.get("/api/signals/{ticker}/similar")
async def get_similar_signals(
    ticker: str,
    direction: str = Query(..., description="CALL or PUT — the direction we're scouting"),
    rsi: float = Query(..., description="RSI value of the bar we're matching"),
    score: int = Query(..., ge=3, le=5, description="Signal strength of the bar we're matching"),
    rsi_band: float = Query(default=5.0, ge=0.5, le=20.0, description="±RSI tolerance"),
    limit: int = Query(default=10, ge=1, le=100, description="Max recent matches to return"),
):
    """Return historical signals similar to the supplied bar's conditions.

    The "similar" predicate is intentionally simple: same ticker + same
    direction + same signal_strength bucket + RSI within ±band. It uses
    the (ticker, signal_strength) and (ticker, trade_type, entry_time)
    indexes — sub-100ms regardless of total row count.
    """
    if not _CLOUD_SQL:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloud SQL not configured — /similar requires the "
                "historical_signals table. Set CLOUD_SQL_CONNECTION_NAME."
            ),
        )

    direction_norm = direction.upper()
    if direction_norm not in ("CALL", "PUT"):
        raise HTTPException(status_code=400, detail="direction must be CALL or PUT")

    ticker_upper = ticker.upper()
    rsi_lo = rsi - rsi_band
    rsi_hi = rsi + rsi_band

    from gcp.database import query_to_dataframe  # lazy import

    where = (
        "ticker = :ticker AND UPPER(trade_type) = :direction "
        "AND signal_strength = :score AND entry_rsi BETWEEN :rsi_lo AND :rsi_hi"
    )
    params = {
        "ticker": ticker_upper,
        "direction": direction_norm,
        "score": score,
        "rsi_lo": rsi_lo,
        "rsi_hi": rsi_hi,
    }

    # Aggregated stats — one query, server-side percentiles.
    stats_df = query_to_dataframe(
        f"""
        SELECT
          COUNT(*)                                              AS count,
          AVG(return_pct)                                       AS avg_mfe_pct,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY return_pct) AS median_mfe_pct,
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY return_pct) AS p25_mfe_pct,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY return_pct) AS p75_mfe_pct,
          AVG(return_5min)                                      AS avg_return_5min,
          AVG(return_20min)                                     AS avg_return_20min,
          SUM(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS pct_profitable,
          MIN(entry_time)                                       AS earliest,
          MAX(entry_time)                                       AS latest
        FROM historical_signals
        WHERE {where}
        """,
        params,
    )

    if stats_df.empty or int(stats_df.iloc[0]["count"]) == 0:
        return {
            "ticker": ticker_upper,
            "direction": direction_norm,
            "rsi": rsi,
            "score": score,
            "rsi_band": rsi_band,
            "stats": {"count": 0},
            "matches": [],
        }

    s = stats_df.iloc[0]
    stats = {
        "count": int(s["count"]),
        "avg_mfe_pct": _f(s["avg_mfe_pct"]),
        "median_mfe_pct": _f(s["median_mfe_pct"]),
        "p25_mfe_pct": _f(s["p25_mfe_pct"]),
        "p75_mfe_pct": _f(s["p75_mfe_pct"]),
        "avg_return_5min": _f(s["avg_return_5min"]),
        "avg_return_20min": _f(s["avg_return_20min"]),
        "pct_profitable": _f(s["pct_profitable"]),
        "earliest": str(s["earliest"]) if pd.notnull(s["earliest"]) else None,
        "latest": str(s["latest"]) if pd.notnull(s["latest"]) else None,
    }

    # Recent matches — same WHERE + LIMIT, ORDER BY entry_time DESC.
    matches_df = query_to_dataframe(
        f"""
        SELECT entry_time AS time,
               UPPER(trade_type) AS direction,
               entry_price AS price,
               signal_strength AS score,
               entry_rsi AS rsi,
               return_pct,
               return_5min,
               return_20min
        FROM historical_signals
        WHERE {where}
        ORDER BY entry_time DESC
        LIMIT :limit
        """,
        {**params, "limit": limit},
    )
    if not matches_df.empty:
        matches_df["time"] = matches_df["time"].astype(str)
    matches = matches_df.where(pd.notnull(matches_df), other=None).to_dict(orient="records")

    return {
        "ticker": ticker_upper,
        "direction": direction_norm,
        "rsi": rsi,
        "score": score,
        "rsi_band": rsi_band,
        "stats": stats,
        "matches": matches,
    }


def _f(v) -> Optional[float]:
    """Cast a numpy/pandas scalar to plain float, or None on NaN."""
    if v is None or pd.isna(v):
        return None
    return float(v)
