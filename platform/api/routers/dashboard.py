"""
Dashboard aggregation router.
GET /api/dashboard/brief/{ticker} - Daily bias / strat status from Cloud SQL
"""
import sys
import logging
from datetime import datetime
from pathlib import Path

from typing import Optional
from fastapi import APIRouter, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

router = APIRouter()
logger = logging.getLogger(__name__)

# Cloud SQL availability (same pattern as main.py)
_CLOUD_SQL = False
_query_fn = None
try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _CLOUD_SQL = is_cloud_sql_configured()
    if _CLOUD_SQL:
        _query_fn = query_to_dataframe
except Exception:
    pass


@router.get("/api/dashboard/brief/{ticker}")
async def dashboard_brief(
    ticker: str,
    date: Optional[str] = Query(None, description="Historical date as YYYY-MM-DD. If omitted, returns latest."),
):
    """Return daily bias / strat status for the dashboard.

    Pulls from premarket_analysis and market_data_daily in Cloud SQL.
    If `date` is provided, returns the brief as of that trading day.
    If Cloud SQL is unavailable, returns source='unavailable' so the
    frontend can show an explicit alert — no silent fallbacks.
    """
    ticker = ticker.upper()

    if not _CLOUD_SQL or _query_fn is None:
        return {
            "ticker": ticker,
            "source": "unavailable",
            "reason": "Cloud SQL not connected. Check CLOUD_SQL_CONNECTION_NAME env var.",
        }

    # --- Premarket analysis (most recent, or as of date) ---
    premarket = {}
    try:
        if date:
            df = _query_fn(
                "SELECT * FROM premarket_analysis "
                "WHERE ticker = :ticker AND analysis_date <= :date "
                "ORDER BY analysis_date DESC LIMIT 1",
                {"ticker": ticker, "date": date},
            )
        else:
            df = _query_fn(
                "SELECT * FROM premarket_analysis "
                "WHERE ticker = :ticker ORDER BY analysis_date DESC LIMIT 1",
                {"ticker": ticker},
            )
        if not df.empty:
            row = df.iloc[0]
            premarket = {
                "analysis_date": str(row.get("analysis_date", "")),
                "price": float(row["price"]) if "price" in row and row["price"] is not None else None,
                "rsi": round(float(row["rsi"]), 1) if "rsi" in row and row["rsi"] is not None else None,
                "rsi_direction": row.get("rsi_direction"),
                "consecutive_up": int(row["consecutive_up"]) if "consecutive_up" in row and row["consecutive_up"] is not None else 0,
                "consecutive_down": int(row["consecutive_down"]) if "consecutive_down" in row and row["consecutive_down"] is not None else 0,
                "signal_status": row.get("signal_status"),
                "strat_daily": row.get("strat_daily"),
                "strat_combo": row.get("strat_combo"),
                "strat_setup": bool(row.get("strat_setup", False)),
                "ftfc_score": round(float(row["ftfc_score"]), 2) if "ftfc_score" in row and row["ftfc_score"] is not None else None,
                "ftfc_direction": row.get("ftfc_direction"),
            }
    except Exception as e:
        logger.warning("premarket_analysis query failed: %s", e)

    # --- Daily indicators (latest, or as of date) ---
    daily = {}
    try:
        base_cols = (
            "SELECT date, close, rsi_14, ema_9, ema_20, sma_200, "
            "       macd, bb_upper, bb_lower, atr_14, rvol, "
            "       strat_candle, strat_combo, strat_setup, "
            "       ftfc_score, ftfc_direction, "
            "       consecutive_up, consecutive_down, "
            "       price_vs_ema9, price_vs_ema20 "
            "FROM market_data_daily "
        )
        if date:
            df = _query_fn(
                base_cols + "WHERE ticker = :ticker AND date <= :date ORDER BY date DESC LIMIT 1",
                {"ticker": ticker, "date": date},
            )
        else:
            df = _query_fn(
                base_cols + "WHERE ticker = :ticker ORDER BY date DESC LIMIT 1",
                {"ticker": ticker},
            )
        if not df.empty:
            row = df.iloc[0]
            _f = lambda v, d=2: round(float(v), d) if v is not None else None
            # Detect staleness: how many days between the latest row and "today" (or requested date)
            try:
                row_date = row.get("date")
                if hasattr(row_date, "strftime"):
                    row_d = row_date
                else:
                    row_d = datetime.strptime(str(row_date), "%Y-%m-%d").date()
                ref_today = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
                stale_days = (ref_today - row_d).days
            except Exception:
                stale_days = 0
            daily = {
                "date": str(row.get("date", "")),
                "stale_days": stale_days,
                "close": _f(row.get("close")),
                "rsi_14": _f(row.get("rsi_14"), 1),
                "ema_9": _f(row.get("ema_9")),
                "ema_20": _f(row.get("ema_20")),
                "sma_200": _f(row.get("sma_200")),
                "macd": _f(row.get("macd"), 4),
                "atr": _f(row.get("atr_14"), 4),
                "rvol": _f(row.get("rvol")),
                "strat_candle": row.get("strat_candle"),
                "strat_combo": row.get("strat_combo"),
                "strat_setup": bool(row.get("strat_setup")) if row.get("strat_setup") is not None else None,
                "ftfc_score": _f(row.get("ftfc_score")),
                "ftfc_direction": row.get("ftfc_direction"),
                "consecutive_up": int(row["consecutive_up"]) if row.get("consecutive_up") is not None else 0,
                "consecutive_down": int(row["consecutive_down"]) if row.get("consecutive_down") is not None else 0,
                "price_vs_ema9": _f(row.get("price_vs_ema9"), 3),
                "price_vs_ema20": _f(row.get("price_vs_ema20"), 3),
            }
    except Exception as e:
        logger.warning("market_data_daily query failed: %s", e)

    # Derive bias direction from premarket first, then daily indicators
    ftfc_dir = premarket.get("ftfc_direction") or daily.get("ftfc_direction")
    if ftfc_dir in ("bullish",):
        bias = "bullish"
    elif ftfc_dir in ("bearish",):
        bias = "bearish"
    else:
        # Fall back to RSI + price vs EMA for rough bias
        rsi = premarket.get("rsi") or daily.get("rsi_14")
        pve = daily.get("price_vs_ema20")
        if rsi is not None and pve is not None:
            if rsi > 55 and pve > 0:
                bias = "bullish"
            elif rsi < 45 and pve < 0:
                bias = "bearish"
            else:
                bias = "neutral"
        else:
            bias = "neutral"

    return {
        "ticker": ticker,
        "source": "cloud_sql",
        "bias": bias,
        "has_premarket": bool(premarket),
        **premarket,
        "daily_indicators": daily,
    }
