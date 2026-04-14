"""
Options flow router — Cloud SQL reader over etf_options_snapshots (AlphaVantage EOD).

Endpoints
---------
GET /api/options/dates/{ticker}
    Returns up to 1000 most recent snapshot dates that actually have AlphaVantage
    data in Cloud SQL. Never fabricates weekdays. Result is in descending order
    (newest first).

GET /api/options/{ticker}/{date_str}
    Returns the normalized option chain for a given ticker and snapshot date.
    Reads Cloud SQL only — no live AlphaVantage proxy on the request path.
    Data is ingested by `gcp.fetchers.fetch_av_historical_options` via the
    daily GitHub Actions workflow.

Design notes
------------
* Data source: `etf_options_snapshots WHERE data_source='alphavantage'`.
  Yahoo-sourced rows (`data_source IS NULL`) are explicitly excluded.
* Cache: cachetools.TTLCache keyed on (ticker, date). EOD rows are immutable
  once written, so cache hit rate approaches 100% after first request each day.
* Response shape is kept identical to the prior live-proxy implementation so
  the React page needs no contract change. Column mapping:
    option_type ('calls'|'puts') → type ('call'|'put')
    last_price                    → last
"""
import logging
import re
from datetime import date, datetime
from pathlib import Path
import sys

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

# Project root so we can import gcp.database the same way the journal router does.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _HAS_CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception as _exc:  # pragma: no cover - import-time guard
    _HAS_CLOUD_SQL = False
    logging.getLogger(__name__).warning("Cloud SQL unavailable: %s", _exc)

log = logging.getLogger(__name__)
router = APIRouter()

VALID_TICKERS = {"SPY", "IWM", "QQQ", "SPX"}
# Tickers whose Greeks are computed locally (lib.options_greeks) instead of
# coming from AlphaVantage. Must mirror lib.options_greeks.COMPUTE_GREEKS_TICKERS.
COMPUTED_GREEKS_TICKERS = {"SPX", "SPXW", "NDX", "RUT", "XSP"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (ticker, date_str) → response dict; 12h TTL (EOD rows are immutable).
_CHAIN_CACHE: TTLCache = TTLCache(maxsize=512, ttl=43200)
# ticker → list[date_str]; 12h TTL. Dates list only changes once per day when
# the scheduled AV fetcher runs, so long TTL avoids re-running the distinct
# scan on cold caches (which is expensive on db-g1-small without the composite
# (ticker, data_source, snapshot_date) index in place).
_DATES_CACHE: TTLCache = TTLCache(maxsize=16, ttl=43200)


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_cloud_sql() -> None:
    if not _HAS_CLOUD_SQL:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloud SQL is not configured for the platform API. "
                "Set CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME and "
                "restart the server."
            ),
        )


def _validate_ticker(ticker: str) -> str:
    ticker_upper = ticker.upper()
    if ticker_upper not in VALID_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker must be one of {sorted(VALID_TICKERS)}, got '{ticker_upper}'",
        )
    return ticker_upper


def _validate_date(date_str: str) -> date:
    if not DATE_RE.match(date_str):
        raise HTTPException(
            status_code=400,
            detail=f"Date must be in YYYY-MM-DD format, got '{date_str}'",
        )
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: '{date_str}'")


# Map Cloud SQL column names → frontend-expected keys. The frontend
# (greeksCalculator.ts) looks for `type: 'call'|'put'`, `strike`, `open_interest`,
# `gamma`, `vega`, `delta`, `volume`, plus a few others for display.
_COLUMN_ALIAS = {
    "last_price": "last",
}

# Base contract columns (always emitted under their source-column names).
_CONTRACT_COLUMNS = [
    "contract_symbol", "expiration", "strike", "option_type",
    "bid", "ask", "mark", "last_price", "volume", "open_interest",
]
# Greek columns. For computed tickers we emit values from the *_computed
# sidecar columns under the standard names; for AV-native tickers we emit
# the AV columns directly. Either way the frontend keeps reading
# `delta`/`gamma`/etc. unchanged.
_GREEK_COLS = ("implied_volatility", "delta", "gamma", "theta", "vega", "rho")


def _df_to_contracts(df: pd.DataFrame, ticker_upper: str) -> list[dict]:
    """Convert a DataFrame of etf_options_snapshots rows into the JSON shape the
    React page already consumes.

    For tickers in :data:`COMPUTED_GREEKS_TICKERS`, the Greeks are sourced
    from the ``*_computed`` sidecar columns (``delta_computed`` etc.) and
    emitted under the canonical ``delta``/``gamma``/... keys. The original
    AV columns are read but ignored — provenance lives in ``greeks_source``.

    Handles NaN → None, ``option_type`` pluralization, and column aliases.
    """
    if df.empty:
        return []

    df = df.dropna(subset=["option_type", "strike", "expiration"])
    type_map = {"calls": "call", "puts": "put"}

    use_computed = ticker_upper in COMPUTED_GREEKS_TICKERS
    greeks_source = "computed_bsm" if use_computed else "alphavantage"

    import math

    def _clean(val):
        """NaN-safe scalar coercion. df.where(pd.notnull, None) re-coerces
        None back to NaN on float columns, so we handle it per-value."""
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    records: list[dict] = []
    for row in df.to_dict(orient="records"):
        out: dict = {}
        for col in _CONTRACT_COLUMNS:
            if col not in row:
                continue
            key = _COLUMN_ALIAS.get(col, col)
            val = _clean(row[col])
            if col == "option_type":
                out["type"] = type_map.get(str(val).lower() if val else "", val)
                continue
            if col == "expiration" and val is not None:
                if hasattr(val, "strftime"):
                    val = val.strftime("%Y-%m-%d")
                else:
                    val = str(val)
            out[key] = val

        # Greeks: pick AV vs computed source per ticker.
        for greek in _GREEK_COLS:
            src_col = f"{greek}_computed" if use_computed else greek
            out[greek] = _clean(row.get(src_col))

        out["greeks_source"] = greeks_source
        records.append(out)
    return records


# ── endpoints ────────────────────────────────────────────────────────────────

# Widening range schedule used by the dates endpoint. The first query tries a
# 60-day window, then 1y, 3y, 10y, unlimited — stopping as soon as we have a
# reasonable number of dates. This keeps the index scan bounded on large tables
# (critical without the composite (ticker, data_source, snapshot_date) index)
# while still returning the full history if the table is small.
_DATES_WINDOW_DAYS = (60, 365, 1100, 3650, None)
_DATES_MIN_RESULTS = 40  # ≈ 2 months of weekdays


@router.get("/api/options/dates/{ticker}")
async def get_options_dates(ticker: str):
    """Return up to 1000 most-recent snapshot dates that have AlphaVantage data
    in Cloud SQL for the given ticker (newest first).

    Uses a widening-range scan: tries a 60-day window first, expanding to 1y,
    3y, 10y, and then unbounded if fewer than 40 dates are found. This keeps
    cold queries bounded when the covering index on (ticker, data_source,
    snapshot_date) isn't yet in place.
    """
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    cached = _DATES_CACHE.get(ticker_upper)
    if cached is not None:
        return {"ticker": ticker_upper, "dates": cached, "source": "cloud_sql", "cached": True}

    dates: list[str] = []
    window_used: str | None = None
    for days in _DATES_WINDOW_DAYS:
        if days is None:
            sql = """
                SELECT DISTINCT snapshot_date
                FROM   etf_options_snapshots
                WHERE  ticker = :ticker
                  AND  data_source = 'alphavantage'
                ORDER  BY snapshot_date DESC
                LIMIT  1000
            """
            params = {"ticker": ticker_upper}
            window_used = "unbounded"
        else:
            sql = """
                SELECT DISTINCT snapshot_date
                FROM   etf_options_snapshots
                WHERE  ticker = :ticker
                  AND  data_source = 'alphavantage'
                  AND  snapshot_date >= CURRENT_DATE - make_interval(days => :days)
                ORDER  BY snapshot_date DESC
                LIMIT  1000
            """
            params = {"ticker": ticker_upper, "days": days}
            window_used = f"{days}d"

        df = query_to_dataframe(sql, params)
        if not df.empty:
            dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                     for d in df["snapshot_date"].tolist()]
        if len(dates) >= _DATES_MIN_RESULTS or days is None:
            break

    if not dates:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No AlphaVantage options data ingested for {ticker_upper}. "
                "Run `python -m gcp.fetchers.fetch_av_historical_options` or "
                "trigger the 'Fetch Daily Alpha Vantage Options Data' workflow."
            ),
        )

    _DATES_CACHE[ticker_upper] = dates
    return {
        "ticker": ticker_upper,
        "dates": dates,
        "source": "cloud_sql",
        "window": window_used,
        "cached": False,
    }


@router.get("/api/options/{ticker}/{date_str}")
async def get_options(ticker: str, date_str: str):
    """Return the AlphaVantage option chain for `ticker` on `date_str`
    (YYYY-MM-DD) from Cloud SQL.
    """
    ticker_upper = _validate_ticker(ticker)
    parsed_date = _validate_date(date_str)
    _require_cloud_sql()

    cache_key = (ticker_upper, date_str)
    cached = _CHAIN_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    sql = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               implied_volatility_computed,
               delta_computed, gamma_computed, theta_computed,
               vega_computed, rho_computed,
               snapshot_ts
        FROM   etf_options_snapshots
        WHERE  ticker = :ticker
          AND  snapshot_date = :snap_date
          AND  data_source = 'alphavantage'
        ORDER  BY expiration, strike, option_type
    """
    df = query_to_dataframe(sql, {"ticker": ticker_upper, "snap_date": parsed_date})

    if df.empty:
        # Look up the nearest available date for a helpful error message.
        nearest_sql = """
            SELECT MAX(snapshot_date) AS nearest
            FROM   etf_options_snapshots
            WHERE  ticker = :ticker
              AND  data_source = 'alphavantage'
              AND  snapshot_date <= :snap_date
        """
        nearest_df = query_to_dataframe(
            nearest_sql, {"ticker": ticker_upper, "snap_date": parsed_date}
        )
        nearest = None
        if not nearest_df.empty and nearest_df.iloc[0]["nearest"] is not None:
            n = nearest_df.iloc[0]["nearest"]
            nearest = n.strftime("%Y-%m-%d") if hasattr(n, "strftime") else str(n)

        msg = (
            f"No AlphaVantage options data for {ticker_upper} on {date_str}. "
            + (f"Most recent available: {nearest}." if nearest
               else "No earlier data ingested for this ticker.")
        )
        raise HTTPException(status_code=404, detail=msg)

    contracts = _df_to_contracts(df, ticker_upper)

    # Take the max snapshot_ts as the "as of" marker.
    snapshot_ts_val = df["snapshot_ts"].max() if "snapshot_ts" in df.columns else None
    if isinstance(snapshot_ts_val, (pd.Timestamp, datetime)):
        snapshot_timestamp = snapshot_ts_val.isoformat()
    else:
        snapshot_timestamp = date_str

    greeks_source = "computed_bsm" if ticker_upper in COMPUTED_GREEKS_TICKERS else "alphavantage"
    response = {
        "ticker": ticker_upper,
        "date": date_str,
        "options": contracts,
        "snapshot_timestamp": snapshot_timestamp,
        "metadata": {
            "source": "cloud_sql",
            "data_source": "alphavantage",
            "greeks_source": greeks_source,
            "row_count": len(contracts),
        },
    }
    _CHAIN_CACHE[cache_key] = response
    return {**response, "cached": False}
