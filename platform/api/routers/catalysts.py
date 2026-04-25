"""
Catalysts router — Benzinga Calendar API corporate events by ticker.

GET /api/catalysts/events — Fetch catalyst events grouped by date
GET /api/catalysts/ticker/{ticker} — Events for a specific ticker
GET /api/catalysts/types — Available catalyst types and coverage info

NOTE: Benzinga covers earnings, conference calls, guidance, dividends, splits,
IPOs, M&A, FDA approvals, and analyst ratings. It does NOT cover investor
conferences, summits, production updates, shareholder meetings, interim
statements, or business updates. Those require upgrading to Wall Street Horizon
via IBKR TWS API ($49-149/mo). See: https://www.wallstreethorizon.com/ibkr-wsh
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

router = APIRouter()
logger = logging.getLogger(__name__)

CATALYSTS_FILE = PROJECT_ROOT / "data" / "catalysts" / "catalyst_calendar.json"

# Benzinga catalyst types we support
BENZINGA_TYPES = {
    "EARNINGS": {"label": "Earnings", "color": "#e74c3c", "icon": "TrendingUp"},
    "CONFERENCE_CALL": {"label": "Conference Call", "color": "#3498db", "icon": "Phone"},
    "GUIDANCE": {"label": "Guidance", "color": "#f39c12", "icon": "Target"},
    "DIVIDEND": {"label": "Dividend", "color": "#27ae60", "icon": "DollarSign"},
    "SPLIT": {"label": "Split", "color": "#9b59b6", "icon": "Scissors"},
    "IPO": {"label": "IPO", "color": "#1abc9c", "icon": "Rocket"},
    "MERGER_ACQUISITION": {"label": "M&A", "color": "#e67e22", "icon": "GitMerge"},
    "FDA": {"label": "FDA", "color": "#c0392b", "icon": "Shield"},
    "ANALYST_RATING": {"label": "Rating", "color": "#2980b9", "icon": "Star"},
    "ECONOMIC": {"label": "Economic", "color": "#7f8c8d", "icon": "Globe"},
    # Corporate Events API types (investor meetings, conferences, presentations)
    "CORPORATE_EVENT": {"label": "Corp. Event", "color": "#34495e", "icon": "Calendar"},
    "INVESTOR_CONFERENCE": {"label": "Conference", "color": "#8e44ad", "icon": "Users"},
    "SUMMIT": {"label": "Summit", "color": "#16a085", "icon": "Mountain"},
    "SHAREHOLDER_MEETING": {"label": "Shareholder Meeting", "color": "#2c3e50", "icon": "Building"},
    "ANALYST_DAY": {"label": "Analyst Day", "color": "#e74c3c", "icon": "Presentation"},
    "INVESTOR_DAY": {"label": "Investor Day", "color": "#d35400", "icon": "Users"},
    "PRESENTATION": {"label": "Presentation", "color": "#2980b9", "icon": "Monitor"},
    "BUSINESS_UPDATE": {"label": "Business Update", "color": "#f39c12", "icon": "Briefcase"},
    "WEBCAST": {"label": "Webcast", "color": "#1abc9c", "icon": "Video"},
}

# WSH types that may still need upgrade for full coverage
WSH_ONLY_TYPES = {
    "PRODUCTION_UPDATE": {"label": "Production Update", "color": "#d35400", "icon": "Factory"},
    "INTERIM_STATEMENT": {"label": "Interim Statement", "color": "#c0392b", "icon": "FileText"},
    "SALES_UPDATE": {"label": "Sales Update", "color": "#27ae60", "icon": "BarChart"},
}


def _load_cached_events():
    """Load catalyst events from the local JSON cache."""
    if not CATALYSTS_FILE.exists():
        return None
    try:
        with open(CATALYSTS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load catalysts cache: %s", e)
        return None


def _fetch_live_events(date_from, date_to, tickers=None, calendar_types=None):
    """Fetch fresh catalyst events from Benzinga API."""
    api_key = os.environ.get("BENZINGA_API_KEY", "")
    if not api_key:
        return None

    try:
        from scripts.fetch_catalyst_calendar import fetch_all_catalysts, save_catalysts
    except ImportError:
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            from fetch_catalyst_calendar import fetch_all_catalysts, save_catalysts
        except ImportError:
            logger.error("fetch_catalyst_calendar module not found")
            return None

    events = fetch_all_catalysts(api_key, date_from, date_to, tickers, calendar_types)
    if events:
        save_catalysts(events)
    return events


@router.get("/api/catalysts/events")
async def get_catalyst_events(
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    tickers: Optional[str] = Query(None, description="Comma-separated tickers"),
    types: Optional[str] = Query(None, description="Comma-separated catalyst types"),
    refresh: bool = Query(False, description="Force refresh from Benzinga API"),
):
    """Get catalyst events grouped by date.

    Returns events from local cache by default. Pass refresh=true to fetch live
    from Benzinga API (requires BENZINGA_API_KEY).
    """
    today = datetime.now()
    d_from = date_from or (today - timedelta(days=3)).strftime("%Y-%m-%d")
    d_to = date_to or (today + timedelta(days=14)).strftime("%Y-%m-%d")
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
    type_list = [t.strip().upper() for t in types.split(",")] if types else None

    events = None

    # Try live fetch if refresh requested or no cache
    if refresh or not CATALYSTS_FILE.exists():
        events = _fetch_live_events(d_from, d_to, ticker_list)

    # Fall back to cache
    if events is None:
        cached = _load_cached_events()
        if cached:
            events = cached.get("events", [])
        else:
            return {
                "status": "no_data",
                "message": "No catalyst data available. Set BENZINGA_API_KEY and call with refresh=true.",
                "events_by_date": {},
                "total": 0,
            }

    # Apply filters
    filtered = events
    if d_from:
        filtered = [e for e in filtered if e.get("date", "") >= d_from]
    if d_to:
        filtered = [e for e in filtered if e.get("date", "") <= d_to]
    if ticker_list:
        filtered = [e for e in filtered if e.get("ticker", "").upper() in ticker_list]
    if type_list:
        filtered = [e for e in filtered if e.get("catalyst_type", "").upper() in type_list]

    # Group by date
    by_date = {}
    for event in filtered:
        date = event.get("date", "unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(event)

    # Sort dates
    sorted_dates = dict(sorted(by_date.items()))

    return {
        "status": "ok",
        "source": "Benzinga",
        "date_range": {"from": d_from, "to": d_to},
        "total": len(filtered),
        "events_by_date": sorted_dates,
    }


@router.get("/api/catalysts/ticker/{ticker}")
async def get_catalysts_for_ticker(
    ticker: str,
    days_back: int = Query(7, description="Days back from today"),
    days_ahead: int = Query(30, description="Days ahead from today"),
):
    """Get all catalyst events for a specific ticker."""
    ticker_upper = ticker.upper()
    today = datetime.now()
    d_from = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    d_to = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Try cache first
    cached = _load_cached_events()
    events = cached.get("events", []) if cached else []

    # Filter to ticker and date range
    filtered = [
        e for e in events
        if e.get("ticker", "").upper() == ticker_upper
        and d_from <= e.get("date", "") <= d_to
    ]

    if not filtered:
        # Try live fetch
        live = _fetch_live_events(d_from, d_to, [ticker_upper])
        if live:
            filtered = [e for e in live if e.get("ticker", "").upper() == ticker_upper]

    return {
        "ticker": ticker_upper,
        "date_range": {"from": d_from, "to": d_to},
        "total": len(filtered),
        "events": sorted(filtered, key=lambda e: e.get("date", "")),
    }


@router.get("/api/catalysts/snapshot/{ticker}")
async def get_catalyst_snapshot(
    ticker: str,
    as_of: Optional[str] = Query(
        None, description="Point-in-time snapshot date YYYY-MM-DD (default: today)"
    ),
    window_days: int = Query(
        7, description="Lookback window for news/SEC/insider events (default 7d)"
    ),
):
    """Unified point-in-time catalyst snapshot for a ticker.

    Returns *only* data that would have been visible on or before `as_of`,
    pulled from news_sentiment, sec_filings, insider_transactions,
    earnings_calendar, earnings_history, and market_data_daily. Use this
    to answer "what would have appeared on the catalyst screen for AVGO
    on April 7?".

    Window: news/SEC/insider events from `as_of - window_days` through
    `as_of`. Earnings calendar is forward-looking (the next 30 days from
    `as_of`). Earnings history is the most recent quarterly result on or
    before `as_of`.
    """
    from datetime import date as _date
    from gcp.database import query_to_dataframe

    tk = ticker.upper()
    try:
        cutoff = _date.fromisoformat(as_of) if as_of else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD")
    window_start = cutoff - timedelta(days=window_days)

    def _df_to_records(df):
        if df is None or df.empty:
            return []
        # pandas NaN/NaT aren't JSON-encodable; replace with None so
        # FastAPI's json.dumps doesn't 500 on the response.
        import math
        recs = df.where(df.notna(), None).to_dict(orient="records")
        for r in recs:
            for k, v in list(r.items()):
                if isinstance(v, float) and math.isnan(v):
                    r[k] = None
        return recs

    def _safe(fn):
        try:
            return fn()
        except Exception as exc:
            logger.warning("snapshot section failed: %s", exc)
            return []

    news = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT published_ts, title, url, source,
               overall_sentiment_label, sentiment_score, relevance_score,
               topics
        FROM news_sentiment
        WHERE ticker = :tk
          AND published_ts <= CAST(:cutoff AS timestamptz) + INTERVAL '23 hours 59 minutes'
          AND published_ts >= CAST(:start AS timestamptz)
        ORDER BY published_ts DESC
        LIMIT 50
        """,
        {"tk": tk, "cutoff": str(cutoff), "start": str(window_start)},
    )))

    sec_filings = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT filing_date, form, items, primary_doc, accession_number
        FROM sec_filings
        WHERE ticker = :tk
          AND filing_date <= CAST(:cutoff AS date)
          AND filing_date >= CAST(:start AS date)
        ORDER BY filing_date DESC
        """,
        {"tk": tk, "cutoff": str(cutoff), "start": str(window_start)},
    )))

    insider = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT transaction_date, executive, title, transaction_type,
               shares, share_price, transaction_value
        FROM insider_transactions
        WHERE ticker = :tk
          AND transaction_date <= CAST(:cutoff AS date)
          AND transaction_date >= CAST(:start AS date)
        ORDER BY transaction_date DESC, transaction_value DESC NULLS LAST
        LIMIT 50
        """,
        {"tk": tk, "cutoff": str(cutoff), "start": str(window_start)},
    )))

    next_earnings = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT earnings_date, earnings_time, eps_estimate
        FROM earnings_calendar
        WHERE ticker = :tk
          AND earnings_date >= CAST(:cutoff AS date)
          AND earnings_date <= CAST(:cutoff AS date) + INTERVAL '90 days'
        ORDER BY earnings_date
        LIMIT 1
        """,
        {"tk": tk, "cutoff": str(cutoff)},
    )))

    last_earnings = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT reported_date, fiscal_date_ending, reported_eps,
               estimated_eps, surprise, surprise_pct
        FROM earnings_history
        WHERE ticker = :tk
          AND reported_date <= CAST(:cutoff AS date)
        ORDER BY reported_date DESC
        LIMIT 4
        """,
        {"tk": tk, "cutoff": str(cutoff)},
    )))

    price_context = _safe(lambda: _df_to_records(query_to_dataframe(
        """
        SELECT date, open, high, low, close, volume,
               rsi_14, ema_20, sma_200
        FROM market_data_daily
        WHERE ticker = :tk
          AND date <= CAST(:cutoff AS date)
          AND date >= CAST(:cutoff AS date) - INTERVAL '10 days'
        ORDER BY date DESC
        """,
        {"tk": tk, "cutoff": str(cutoff)},
    )))

    return {
        "ticker": tk,
        "as_of": str(cutoff),
        "window_start": str(window_start),
        "window_days": window_days,
        "news": news,
        "sec_filings": sec_filings,
        "insider_transactions": insider,
        "next_earnings": next_earnings[0] if next_earnings else None,
        "earnings_history_recent": last_earnings,
        "price_context_daily": price_context,
        "counts": {
            "news_articles": len(news),
            "sec_filings": len(sec_filings),
            "insider_transactions": len(insider),
            "earnings_history": len(last_earnings),
            "price_bars": len(price_context),
        },
    }


@router.get("/api/catalysts/types")
async def get_catalyst_types():
    """Return available catalyst types and WSH upgrade info."""
    return {
        "benzinga_types": BENZINGA_TYPES,
        "wsh_only_types": WSH_ONLY_TYPES,
        "upgrade_note": (
            "Benzinga covers earnings, conference calls, guidance, dividends, "
            "splits, IPOs, M&A, FDA, ratings, and economics. For investor "
            "conferences, summits, production updates, shareholder meetings, "
            "interim statements, and business updates, upgrade to Wall Street "
            "Horizon via IBKR TWS API ($49-149/mo). "
            "See: https://www.wallstreethorizon.com/ibkr-wsh"
        ),
    }
