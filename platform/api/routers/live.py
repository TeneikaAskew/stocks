"""
Live market data router.
GET /api/live/quote/{ticker} - Alpha Vantage GLOBAL_QUOTE (real-time quote)
GET /api/live/history/{ticker} - Alpha Vantage TIME_SERIES_INTRADAY 1min (last 100 bars for indicator calculation)
GET /api/live/avg-volume/{ticker} - 20-day average daily volume (for RVOL denominator)
GET /api/live/status - market open/closed status based on Eastern Time
"""
import logging
import os
import sys
from datetime import datetime, time, date
from pathlib import Path

import httpx
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from zoneinfo import ZoneInfo

# Project root so we can import gcp.database alongside the other routers.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception:
    _CLOUD_SQL = False
    query_to_dataframe = None  # type: ignore[assignment]

# Canonical indicator implementations — single source of truth.
from lib.indicators import (
    add_signal_indicators,
    calculate_atr,
    calculate_ema,
    calculate_rsi,
    calculate_stoch_rsi,
    calculate_vwap,
)

# Canonical per-bar signal voter — the SAME function gcp/signal_monitor.py
# calls (mean-reversion, 3-of-5 condition scoring) so the Charts "Sig"
# overlay fires from the identical Python code path production alerting
# uses. See lib/signals.py module docstring.
from lib.signals import generate_signals

log = logging.getLogger(__name__)
router = APIRouter()

AV_API_KEY = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
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


@router.get("/api/live/avg-volume/{ticker}")
async def get_avg_volume(ticker: str):
    """Return the 20-day average daily volume for RVOL calculation.

    Strategy: Cloud SQL `market_data_daily` if configured, otherwise fall back
    to AlphaVantage TIME_SERIES_DAILY (compact = last 100 days).
    """
    ticker_upper = ticker.upper()

    # ── Cloud SQL primary ────────────────────────────────────────────────────
    if _CLOUD_SQL and query_to_dataframe is not None:
        try:
            df = query_to_dataframe(
                """
                SELECT date, volume
                FROM market_data_daily
                WHERE ticker = :ticker AND volume IS NOT NULL
                ORDER BY date DESC LIMIT 20
                """,
                {"ticker": ticker_upper},
            )
            if not df.empty and len(df) >= 5:
                avg_vol = float(df["volume"].mean())
                last_date = df.iloc[0]["date"]
                last_str = last_date.strftime("%Y-%m-%d") if hasattr(last_date, "strftime") else str(last_date)
                return {
                    "ticker": ticker_upper,
                    "avg_volume_20d": avg_vol,
                    "sample_size": int(len(df)),
                    "last_date": last_str,
                    "source": "cloud_sql",
                }
        except Exception as exc:
            log.warning("avg-volume Cloud SQL lookup failed for %s: %s", ticker_upper, exc)

    # ── AlphaVantage fallback ────────────────────────────────────────────────
    if not AV_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="No Cloud SQL history and Alpha Vantage API key not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(AV_BASE, params={
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker_upper,
                "outputsize": "compact",
                "apikey": AV_API_KEY,
            })
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="Alpha Vantage request timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage request failed: {exc}")

    if "Note" in data or "Information" in data:
        raise HTTPException(status_code=429, detail="Alpha Vantage rate limit")
    if "Error Message" in data:
        raise HTTPException(status_code=400, detail=f"Alpha Vantage error: {data['Error Message']}")

    series = data.get("Time Series (Daily)", {})
    if not series:
        raise HTTPException(status_code=404, detail=f"No daily history for {ticker_upper}")

    # Take the 20 most recent trading days
    sorted_dates = sorted(series.keys(), reverse=True)[:20]
    volumes = []
    for d in sorted_dates:
        try:
            volumes.append(float(series[d]["5. volume"]))
        except (KeyError, ValueError):
            continue

    if not volumes:
        raise HTTPException(status_code=502, detail="No usable volume rows in AV response")

    return {
        "ticker": ticker_upper,
        "avg_volume_20d": sum(volumes) / len(volumes),
        "sample_size": len(volumes),
        "last_date": sorted_dates[0] if sorted_dates else None,
        "source": "alphavantage",
    }


# ── Indicators + Signals (single source of truth — never compute client-side) ─

class _Bar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class _IndicatorsRequest(BaseModel):
    bars: list[_Bar]
    current_price: float | None = None
    current_volume: float | None = None
    avg_volume_20d: float | None = None


def _last(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    if pd.isna(v):
        return None
    return float(v)


def _make_condition(
    cid: str,
    label: str,
    current: float | None,
    threshold: float | None,
    op: str,
) -> dict:
    met = False
    if current is not None and threshold is not None:
        met = (current > threshold) if op == ">" else (current < threshold)
    return {
        "id": cid,
        "label": label,
        "met": met,
        "current": current,
        "threshold": threshold,
        "operator": op,
    }


@router.post("/api/live/indicators")
def compute_live_indicators(req: _IndicatorsRequest) -> dict:
    """Compute indicators and CALL/PUT signals from a bar series.

    The frontend sends the bars it already has (live history or historical
    review slice). This endpoint runs the canonical indicator library
    (`lib/indicators.py`) and the dashboard signal logic server-side so
    TS and Python stay in lockstep — there is no duplicate math in the app.
    """
    bars = req.bars
    if len(bars) == 0:
        empty_ind = {
            "ema9": None,
            "ema20": None,
            "ema50": None,
            "rsi": None,
            "stochK": None,
            "stochD": None,
            "atr": None,
            "vwap": None,
        }
        return {"indicators": empty_ind, "signals": _empty_signals()}

    # Assemble Series — aligned, no index mismatches.
    closes = pd.Series([b.close for b in bars], dtype=float)
    highs = pd.Series([b.high for b in bars], dtype=float)
    lows = pd.Series([b.low for b in bars], dtype=float)
    volumes = pd.Series([b.volume for b in bars], dtype=float)
    # VWAP in lib/indicators resets per session; group bars by calendar date.
    dates = pd.Series([b.time[:10] for b in bars])

    ema9 = calculate_ema(closes, 9)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    rsi_series = calculate_rsi(closes, 14)
    stoch_k, stoch_d = calculate_stoch_rsi(rsi_series, period=14, k_period=3, d_period=3)
    atr_series = calculate_atr(highs, lows, closes, period=14)
    vwap_series = calculate_vwap(highs, lows, closes, volumes, dates)

    # Previous-bar StochRSI K for crossover checks in playbook conditions.
    prev_stoch_k = None
    if len(stoch_k) >= 2:
        v = stoch_k.iloc[-2]
        prev_stoch_k = None if pd.isna(v) else float(v)

    indicators = {
        "ema9": _last(ema9),
        "ema20": _last(ema20),
        "ema50": _last(ema50),
        "rsi": _last(rsi_series),
        "stochK": _last(stoch_k),
        "stochD": _last(stoch_d),
        "atr": _last(atr_series),
        "vwap": _last(vwap_series),
        "stochKPrev": prev_stoch_k,
    }

    price = req.current_price if req.current_price is not None else float(closes.iloc[-1])
    vol = req.current_volume
    rvol = None
    if vol is not None and req.avg_volume_20d and req.avg_volume_20d > 0:
        rvol = vol / req.avg_volume_20d

    signals = _build_signals(price, indicators, rvol)
    return {"indicators": indicators, "signals": signals}


@router.post("/api/live/signal-series")
def compute_live_signal_series(req: _IndicatorsRequest) -> dict:
    """Per-bar CALL/PUT signal fires for the Charts page "Sig" overlay.

    Reuses the SAME Python code path ``gcp/signal_monitor.py`` drives for
    live alerting — no re-derived TS math:
      * ``lib.indicators.add_signal_indicators`` — the exact indicator
        engine ``SignalMonitor.calculate_indicators`` calls (ATR, RSI,
        EMAs, VWAP, RVOL, OBV, StochRSI, MACD, consecutive moves, price
        levels).
      * ``lib.signals.generate_signals`` — batches ``evaluate_signal``
        (the mean-reversion 3-of-5 condition voter
        ``SignalMonitor._evaluate_strategies_for_bar`` calls per live bar)
        across every eligible row.

    Uses default (uncalibrated) ``IndicatorConfig``/``SignalConfig`` — this
    endpoint is ticker-agnostic (no ``ticker`` in the request body) so it
    can't resolve the per-ticker Tier-A calibration
    (``lib.strategies.calibration.get_consecutive_periods`` /
    ``get_call_rsi_range`` / ``get_put_rsi_range``) production uses, which
    also requires a DB round-trip this endpoint deliberately avoids (Rule
    0: one request = one in-memory pandas pass over <= ~400 rows, no DB,
    no external calls). This matches the previous client-side TS voter,
    which was likewise not per-ticker-calibrated.
    """
    bars = req.bars
    if len(bars) < 14:
        raise HTTPException(status_code=422, detail="need >= 14 bars for indicator warm-up")

    df = pd.DataFrame({
        "Time": [b.time for b in bars],
        "Open": [b.open for b in bars],
        "High": [b.high for b in bars],
        "Low": [b.low for b in bars],
        "Close": [b.close for b in bars],
        "Volume": [b.volume for b in bars],
    })
    df = add_signal_indicators(df, close_col="Close")
    signals_df = generate_signals(df)

    fires: list[dict] = []
    if not signals_df.empty:
        for _, row in signals_df.iterrows():
            fires.append({
                "time": str(row["time"]),
                "direction": row["direction"],
                "score": float(row["total_score"]),
            })
    return {"fires": fires}


def _empty_signals() -> dict:
    empty = {"direction": "", "strength": 0, "conditions": [], "fired": False}
    return {
        "call": {**empty, "direction": "CALL"},
        "put": {**empty, "direction": "PUT"},
    }


def _build_signals(price: float | None, ind: dict, rvol: float | None) -> dict:
    """Trend-following CALL/PUT conditions — ported from
    platform/src/lib/indicators.ts so UI behavior is preserved exactly."""
    call_conds = [
        _make_condition("c_p_ema9", "Price > EMA9", price, ind["ema9"], ">"),
        _make_condition("c_p_ema20", "Price > EMA20", price, ind["ema20"], ">"),
        _make_condition("c_p_ema50", "Price > EMA50", price, ind["ema50"], ">"),
        _make_condition("c_p_vwap", "Price > VWAP", price, ind["vwap"], ">"),
        _make_condition("c_rsi50", "RSI > 50", ind["rsi"], 50.0, ">"),
        _make_condition("c_rsi60", "RSI > 60", ind["rsi"], 60.0, ">"),
        _make_condition("c_stoch70", "StochRSI > 70", ind["stochK"], 70.0, ">"),
        _make_condition("c_rvol", "RVOL > 1.0", rvol, 1.0, ">"),
        _make_condition("c_cross", "EMA9 > EMA20", ind["ema9"], ind["ema20"], ">"),
        _make_condition("c_atr", "ATR > 2.0", ind["atr"], 2.0, ">"),
    ]
    put_conds = [
        _make_condition("p_p_ema9", "Price < EMA9", price, ind["ema9"], "<"),
        _make_condition("p_p_ema20", "Price < EMA20", price, ind["ema20"], "<"),
        _make_condition("p_p_ema50", "Price < EMA50", price, ind["ema50"], "<"),
        _make_condition("p_p_vwap", "Price < VWAP", price, ind["vwap"], "<"),
        _make_condition("p_rsi50", "RSI < 50", ind["rsi"], 50.0, "<"),
        _make_condition("p_rsi40", "RSI < 40", ind["rsi"], 40.0, "<"),
        _make_condition("p_stoch30", "StochRSI < 30", ind["stochK"], 30.0, "<"),
        _make_condition("p_rvol", "RVOL > 1.0", rvol, 1.0, ">"),
        _make_condition("p_cross", "EMA9 < EMA20", ind["ema9"], ind["ema20"], "<"),
        _make_condition("p_atr", "ATR > 2.0", ind["atr"], 2.0, ">"),
    ]
    call_strength = round(sum(1 for c in call_conds if c["met"]) / len(call_conds) * 100)
    put_strength = round(sum(1 for c in put_conds if c["met"]) / len(put_conds) * 100)
    return {
        "call": {
            "direction": "CALL",
            "conditions": call_conds,
            "strength": call_strength,
            "fired": call_strength >= 70,
        },
        "put": {
            "direction": "PUT",
            "conditions": put_conds,
            "strength": put_strength,
            "fired": put_strength >= 70,
        },
    }
