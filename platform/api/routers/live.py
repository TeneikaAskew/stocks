"""
Live market data router.
GET /api/live/quote/{ticker} - Alpha Vantage GLOBAL_QUOTE (real-time quote)
GET /api/live/history/{ticker} - Alpha Vantage TIME_SERIES_INTRADAY 1min (last 100 bars for indicator calculation)
GET /api/live/status - market open/closed status based on Eastern Time
"""
import os
from datetime import datetime, time, date

import httpx
from fastapi import APIRouter, HTTPException
from zoneinfo import ZoneInfo

router = APIRouter()

AV_API_KEY = os.environ.get("AV_API_KEY", "")
AV_BASE = "https://www.alphavantage.co/query"

ET_TZ = ZoneInfo("America/New_York")

# Regular market hours in Eastern Time
MARKET_OPEN = time(9, 30, 0)
MARKET_CLOSE = time(16, 0, 0)

# US market holidays (add more as needed)
MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 11, 27), # Black Friday (early close, treated as closed)
    date(2026, 12, 25), # Christmas
}


def _is_market_open(now_et: datetime) -> tuple[bool, str]:
    """Return (is_open, session) for the given Eastern Time datetime."""
    today = now_et.date()
    current_time = now_et.time()

    # Weekends
    if today.weekday() >= 5:
        return False, "closed"

    # Holidays
    if today in MARKET_HOLIDAYS_2026:
        return False, "closed"

    # Regular session
    if MARKET_OPEN <= current_time < MARKET_CLOSE:
        return True, "regular"

    # Pre-market: 4:00 AM - 9:30 AM ET
    if time(4, 0, 0) <= current_time < MARKET_OPEN:
        return False, "pre-market"

    # After-hours: 4:00 PM - 8:00 PM ET
    if MARKET_CLOSE <= current_time < time(20, 0, 0):
        return False, "after-hours"

    return False, "closed"


def _next_open_et(now_et: datetime) -> str | None:
    """Return the next market open as ISO string, or None if market is currently open."""
    is_open, _ = _is_market_open(now_et)
    if is_open:
        return None

    # Walk forward day by day until we find a trading day
    check = now_et.date()
    # If today after close, start from tomorrow
    if now_et.time() >= MARKET_CLOSE and check.weekday() < 5:
        import datetime as dt
        check = check + dt.timedelta(days=1)

    import datetime as dt
    for _ in range(10):
        if check.weekday() < 5 and check not in MARKET_HOLIDAYS_2026:
            next_open = datetime.combine(check, MARKET_OPEN)
            return next_open.strftime("%Y-%m-%d %H:%M:%S")
        check = check + dt.timedelta(days=1)

    return None


@router.get("/api/live/status")
async def get_market_status():
    """Return current market open/closed status based on Eastern Time."""
    now_et = datetime.now(ET_TZ)
    is_open, session = _is_market_open(now_et)
    next_open = _next_open_et(now_et)

    return {
        "is_open": is_open,
        "session": session,
        "next_open": next_open,
        "current_time_et": now_et.strftime("%H:%M:%S"),
    }


@router.get("/api/live/quote/{ticker}")
async def get_live_quote(ticker: str):
    """Fetch real-time quote from Alpha Vantage GLOBAL_QUOTE."""
    ticker_upper = ticker.upper()

    if not AV_API_KEY:
        raise HTTPException(status_code=503, detail="Alpha Vantage API key not configured")

    now_et = datetime.now(ET_TZ)
    is_open, session = _is_market_open(now_et)

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker_upper,
        "apikey": AV_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="Alpha Vantage request timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage request failed: {exc}")

    # Check for API-level errors
    if "Note" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage rate limit: {data['Note']}")
    if "Information" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage limit: {data['Information']}")
    if "Error Message" in data:
        raise HTTPException(status_code=400, detail=f"Alpha Vantage error: {data['Error Message']}")

    quote = data.get("Global Quote", {})
    if not quote:
        status_code = 503 if not is_open else 404
        raise HTTPException(status_code=status_code, detail=f"No quote data returned for {ticker_upper}")

    def _float(val: str) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    price = _float(quote.get("05. price", "0"))
    prev_close = _float(quote.get("08. previous close", "0"))
    change = _float(quote.get("09. change", "0"))
    change_raw = quote.get("10. change percent", "0%").rstrip("%")
    change_pct = _float(change_raw)

    return {
        "ticker": ticker_upper,
        "price": price,
        "open": _float(quote.get("02. open", "0")),
        "high": _float(quote.get("03. high", "0")),
        "low": _float(quote.get("04. low", "0")),
        "volume": int(_float(quote.get("06. volume", "0"))),
        "change": change,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "last_updated": quote.get("07. latest trading day", ""),
        "market_session": session,
        "market_open": is_open,
    }


@router.get("/api/live/history/{ticker}")
async def get_live_history(ticker: str):
    """Fetch last 100 1-min bars from Alpha Vantage TIME_SERIES_INTRADAY."""
    ticker_upper = ticker.upper()

    if not AV_API_KEY:
        raise HTTPException(status_code=503, detail="Alpha Vantage API key not configured")

    now_et = datetime.now(ET_TZ)
    is_open, session = _is_market_open(now_et)

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": ticker_upper,
        "interval": "1min",
        "outputsize": "compact",
        "apikey": AV_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="Alpha Vantage request timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage request failed: {exc}")

    # Check for API-level errors
    if "Note" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage rate limit: {data['Note']}")
    if "Information" in data:
        raise HTTPException(status_code=429, detail=f"Alpha Vantage limit: {data['Information']}")
    if "Error Message" in data:
        raise HTTPException(status_code=400, detail=f"Alpha Vantage error: {data['Error Message']}")

    time_series = data.get("Time Series (1min)", {})
    if not time_series:
        status_code = 503 if not is_open else 404
        raise HTTPException(
            status_code=status_code,
            detail=f"No intraday data returned for {ticker_upper}. Market session: {session}",
        )

    bars = []
    for ts in sorted(time_series.keys()):
        bar = time_series[ts]
        try:
            bars.append({
                "time": ts,
                "open": float(bar["1. open"]),
                "high": float(bar["2. high"]),
                "low": float(bar["3. low"]),
                "close": float(bar["4. close"]),
                "volume": int(float(bar["5. volume"])),
            })
        except (KeyError, ValueError):
            continue

    return {
        "ticker": ticker_upper,
        "interval": "1min",
        "count": len(bars),
        "market_session": session,
        "market_open": is_open,
        "bars": bars,
    }
