"""
Options flow router - replaces Cloudflare Worker.
GET /api/options/{ticker}/{date} - Alpha Vantage HISTORICAL_OPTIONS proxy (date: YYYY-MM-DD)
GET /api/options/dates/{ticker} - available dates: returns last 10 trading days (skip weekends)
"""
import os
import re
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

AV_API_KEY = os.environ.get("AV_API_KEY", "")
AV_BASE = "https://www.alphavantage.co/query"

VALID_TICKERS = {"SPY", "IWM", "QQQ"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _last_n_trading_dates(n: int = 10) -> list[str]:
    """Return the last N trading dates (Mon-Fri, no weekends) up to today."""
    result = []
    check = date.today()
    while len(result) < n:
        if check.weekday() < 5:  # Monday=0 … Friday=4
            result.append(check.strftime("%Y-%m-%d"))
        check -= timedelta(days=1)
    return result


@router.get("/api/options/dates/{ticker}")
async def get_options_dates(ticker: str):
    """Return the last 10 trading dates available for options data."""
    ticker_upper = ticker.upper()
    if ticker_upper not in VALID_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker must be one of {sorted(VALID_TICKERS)}, got '{ticker_upper}'",
        )

    dates = _last_n_trading_dates(10)
    return {
        "ticker": ticker_upper,
        "dates": dates,
    }


@router.get("/api/options/{ticker}/{date_str}")
async def get_options(ticker: str, date_str: str):
    """Proxy Alpha Vantage HISTORICAL_OPTIONS for a given ticker and date."""
    ticker_upper = ticker.upper()

    # Validate ticker
    if ticker_upper not in VALID_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker must be one of {sorted(VALID_TICKERS)}, got '{ticker_upper}'",
        )

    # Validate date format
    if not DATE_RE.match(date_str):
        raise HTTPException(
            status_code=400,
            detail=f"Date must be in YYYY-MM-DD format, got '{date_str}'",
        )

    # Validate date is parseable
    try:
        parsed_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: '{date_str}'")

    if parsed_date.weekday() >= 5:
        raise HTTPException(
            status_code=400,
            detail=f"'{date_str}' is a weekend — options markets are closed",
        )

    if not AV_API_KEY:
        raise HTTPException(status_code=503, detail="Alpha Vantage API key not configured")

    params = {
        "function": "HISTORICAL_OPTIONS",
        "symbol": ticker_upper,
        "date": date_str,
        "apikey": AV_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="Alpha Vantage request timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage request failed: {exc}")

    # Check for API-level errors and rate limits
    if "Note" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage rate limit: {data['Note']}")
    if "Information" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage limit: {data['Information']}")
    if "Error Message" in data:
        raise HTTPException(status_code=400, detail=f"Alpha Vantage error: {data['Error Message']}")

    # AV returns {"data": [...], "message": "..."} for HISTORICAL_OPTIONS
    options_list = data.get("data", [])
    message = data.get("message", "")
    metadata = {k: v for k, v in data.items() if k not in ("data",)}

    if not options_list and not message:
        raise HTTPException(
            status_code=404,
            detail=f"No options data returned for {ticker_upper} on {date_str}",
        )

    # Normalise numeric fields so consumers get floats, not strings
    normalised = []
    numeric_fields = {
        "strike", "last", "mark", "bid", "ask", "volume", "open_interest",
        "implied_volatility", "delta", "gamma", "theta", "vega", "rho",
        "bid_size", "ask_size",
    }
    for contract in options_list:
        row = {}
        for key, val in contract.items():
            if key in numeric_fields:
                try:
                    row[key] = float(val) if val not in (None, "", "N/A", "-") else None
                except (TypeError, ValueError):
                    row[key] = None
            else:
                row[key] = val
        normalised.append(row)

    snapshot_timestamp = data.get("snapshot_timestamp") or date_str

    return {
        "ticker": ticker_upper,
        "date": date_str,
        "options": normalised,
        "snapshot_timestamp": snapshot_timestamp,
        "metadata": metadata,
    }
