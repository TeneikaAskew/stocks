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

    # Fall back to cache. If no Benzinga data is available, fall through
    # with an empty list — our own DB sources (news / SEC) below still
    # populate the feed so the page is never blank.
    if events is None:
        cached = _load_cached_events()
        events = cached.get("events", []) if cached else []

    # Apply filters
    filtered = events
    if d_from:
        filtered = [e for e in filtered if e.get("date", "") >= d_from]
    if d_to:
        filtered = [e for e in filtered if e.get("date", "") <= d_to]
    if ticker_list:
        filtered = [e for e in filtered if e.get("ticker", "").upper() in ticker_list]

    # Merge our own DB-sourced catalyst events (news with catalyst topics
    # + 8-K filings with material item codes). These complement Benzinga's
    # earnings/M&A/dividend/IPO coverage with the realtime news stream
    # and SEC filings we now collect ourselves.
    db_events = _db_catalyst_events(d_from, d_to, ticker_list)
    filtered = filtered + db_events

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

    sources = ["Benzinga"]
    if db_events:
        sources.append(f"DB (news + sec, {len(db_events)})")

    return {
        "status": "ok",
        "source": " + ".join(sources),
        "date_range": {"from": d_from, "to": d_to},
        "total": len(filtered),
        "events_by_date": sorted_dates,
    }


# ── DB-sourced catalyst event helpers ───────────────────────────────────────


def _db_catalyst_events(
    d_from: str, d_to: str, ticker_list: Optional[list[str]],
) -> list[dict]:
    """Pull news + 8-K events from Cloud SQL in the date range and shape
    them like Benzinga events so the existing UI renders them.

    Returns one entry per (ticker, day, source-event). News events are
    deduped to one-per-(ticker, day, headline) so the catalyst page
    doesn't drown in re-syndicated articles. 8-K events emit one row
    per filing.
    """
    try:
        from gcp.database import query_to_dataframe
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("DB catalyst lookup failed (db import): %s", exc)
        return []

    out: list[dict] = []

    # ── 1. News with catalyst-tagged topics ───────────────────────────
    news_sql = (
        "SELECT ticker, published_ts::date AS date, title, "
        "       overall_sentiment_label, sentiment_score, "
        "       relevance_score, topics, url "
        "FROM news_sentiment "
        "WHERE published_ts::date BETWEEN CAST(:d_from AS date) "
        "                              AND CAST(:d_to AS date) "
        "  AND relevance_score >= 0.7 "
        "  AND topics && ARRAY['mergers_and_acquisitions','earnings',"
        "                      'ipo','economy_monetary']::TEXT[]"
    )
    params = {"d_from": d_from, "d_to": d_to}
    try:
        news_df = query_to_dataframe(news_sql, params)
    except Exception as exc:
        logger.warning("news catalyst lookup failed: %s", exc)
        news_df = None

    if news_df is not None and not news_df.empty:
        # Filter by ticker_list if provided
        if ticker_list:
            news_df = news_df[news_df["ticker"].str.upper().isin(ticker_list)]
        # Dedupe to one event per (ticker, date, headline)
        seen: set[tuple] = set()
        for _, r in news_df.iterrows():
            tk = str(r.get("ticker") or "").upper()
            if not tk:
                continue
            title = str(r.get("title") or "")[:200]
            key = (tk, str(r["date"]), title)
            if key in seen:
                continue
            seen.add(key)
            topics = list(r.get("topics") or [])
            # Map AV topic to a Benzinga-compatible catalyst_type so
            # the existing TYPE_CONFIG renders a badge cleanly.
            if "mergers_and_acquisitions" in topics:
                cat_type = "MERGER_ACQUISITION"
            elif "ipo" in topics:
                cat_type = "IPO"
            elif "economy_monetary" in topics:
                cat_type = "ECONOMIC"
            elif "earnings" in topics:
                cat_type = "EARNINGS_NEWS"
            else:
                cat_type = "NEWS_CATALYST"
            rel = float(r.get("relevance_score") or 0)
            sent = float(r.get("sentiment_score") or 0)
            impact = "High" if rel >= 0.9 and abs(sent) >= 0.4 else (
                "Medium" if rel >= 0.7 and abs(sent) >= 0.2 else "Low"
            )
            out.append({
                "date": str(r["date"]),
                "ticker": tk,
                "catalyst_type": cat_type,
                "title": title,
                "impact": impact,
                "source": "AV news",
                "url": str(r.get("url") or "") or None,
                "sentiment_label": str(r.get("overall_sentiment_label") or ""),
                "sentiment_score": round(sent, 2),
                "relevance_score": round(rel, 2),
            })

    # ── 2. Economic events (CPI, GDP, FOMC, etc.) ─────────────────────
    econ_sql = (
        "SELECT event_date AS date, event_name AS title, importance, "
        "       country, actual, forecast, previous "
        "FROM economic_events "
        "WHERE event_date BETWEEN CAST(:d_from AS date) "
        "                      AND CAST(:d_to AS date) "
        "  AND COALESCE(importance, '') IN ('high', 'medium')"
    )
    try:
        econ_df = query_to_dataframe(econ_sql, params)
    except Exception as exc:
        logger.warning("economic_events catalyst lookup failed: %s", exc)
        econ_df = None
    if econ_df is not None and not econ_df.empty:
        for _, r in econ_df.iterrows():
            imp = str(r.get("importance") or "medium").lower()
            out.append({
                "date": str(r["date"]),
                "ticker": "MACRO",
                "catalyst_type": "ECONOMIC",
                "title": str(r.get("title") or ""),
                "impact": "High" if imp == "high" else "Medium",
                "source": "FRED/Calendar",
                "country": str(r.get("country") or ""),
                "actual": str(r.get("actual") or ""),
                "forecast": str(r.get("forecast") or ""),
                "previous": str(r.get("previous") or ""),
            })

    # ── 3. Earnings calendar ──────────────────────────────────────────
    earn_sql = (
        "SELECT ticker, earnings_date AS date, company_name, "
        "       earnings_time, eps_estimate "
        "FROM earnings_calendar "
        "WHERE earnings_date BETWEEN CAST(:d_from AS date) "
        "                         AND CAST(:d_to AS date)"
    )
    try:
        earn_df = query_to_dataframe(earn_sql, params)
    except Exception as exc:
        logger.warning("earnings_calendar catalyst lookup failed: %s", exc)
        earn_df = None
    if earn_df is not None and not earn_df.empty:
        if ticker_list:
            earn_df = earn_df[earn_df["ticker"].str.upper().isin(ticker_list)]
        seen_e: set[tuple] = set()
        for _, r in earn_df.iterrows():
            tk = str(r.get("ticker") or "").upper()
            if not tk:
                continue
            key = (tk, str(r["date"]))
            if key in seen_e:
                continue
            seen_e.add(key)
            company = str(r.get("company_name") or tk)
            est = r.get("eps_estimate")
            est_str = f", est {float(est):.2f}" if est not in (None, "") else ""
            out.append({
                "date": str(r["date"]),
                "ticker": tk,
                "catalyst_type": "EARNINGS",
                "title": f"{company} earnings ({r.get('earnings_time') or 'unknown'}{est_str})",
                "impact": "High",
                "source": "AV earnings_calendar",
            })

    # ── 4. Insider clusters (≥3 distinct insiders, same ticker, ──────
    #       same direction, within 3-day rolling window). One event
    #       per (ticker, day, direction).
    insider_sql = (
        "SELECT ticker, transaction_date AS date, "
        "       transaction_type, "
        "       COUNT(DISTINCT executive) AS insiders, "
        "       COUNT(*)                   AS txns, "
        "       SUM(transaction_value)     AS total_value "
        "FROM insider_transactions "
        "WHERE transaction_date BETWEEN CAST(:d_from AS date) "
        "                            AND CAST(:d_to AS date) "
        "GROUP BY ticker, transaction_date, transaction_type "
        "HAVING COUNT(DISTINCT executive) >= 3"
    )
    try:
        ins_df = query_to_dataframe(insider_sql, params)
    except Exception as exc:
        logger.warning("insider_transactions catalyst lookup failed: %s", exc)
        ins_df = None
    if ins_df is not None and not ins_df.empty:
        if ticker_list:
            ins_df = ins_df[ins_df["ticker"].str.upper().isin(ticker_list)]
        for _, r in ins_df.iterrows():
            tk = str(r.get("ticker") or "").upper()
            if not tk:
                continue
            kind = str(r.get("transaction_type") or "")
            cat_type = "INSIDER_BUY" if kind == "A" else "INSIDER_SELL"
            insiders = int(r.get("insiders") or 0)
            total_value = float(r.get("total_value") or 0.0)
            out.append({
                "date": str(r["date"]),
                "ticker": tk,
                "catalyst_type": cat_type,
                "title": (
                    f"{insiders} insider{'s' if insiders > 1 else ''} "
                    f"{'buying' if kind == 'A' else 'selling'} "
                    f"~${total_value/1e6:.1f}M"
                ),
                "impact": "Medium",
                "source": "AV insider",
                "insiders": insiders,
                "total_value": round(total_value, 0),
            })

    # ── 5. 8-K filings with material items ────────────────────────────
    sec_sql = (
        "SELECT ticker, filing_date AS date, form, items, primary_doc, "
        "       accession_number "
        "FROM sec_filings "
        "WHERE filing_date BETWEEN CAST(:d_from AS date) "
        "                       AND CAST(:d_to AS date) "
        "  AND form = '8-K' "
        "  AND items && ARRAY['1.01','2.01','5.02','7.01','8.01']::TEXT[]"
    )
    try:
        sec_df = query_to_dataframe(sec_sql, params)
    except Exception as exc:
        logger.warning("sec_filings catalyst lookup failed: %s", exc)
        sec_df = None

    if sec_df is not None and not sec_df.empty:
        if ticker_list:
            sec_df = sec_df[sec_df["ticker"].str.upper().isin(ticker_list)]
        ITEM_LABELS = {
            "1.01": "Material Definitive Agreement",
            "2.01": "Completed Acquisition / Disposition",
            "5.02": "Officer Departure / Election",
            "7.01": "Reg-FD Disclosure",
            "8.01": "Other Events",
        }
        for _, r in sec_df.iterrows():
            tk = str(r.get("ticker") or "").upper()
            if not tk:
                continue
            items = list(r.get("items") or [])
            labels = [ITEM_LABELS.get(it, it) for it in items if it in ITEM_LABELS]
            if not labels:
                continue
            heavy = any(it in ("1.01", "2.01") for it in items)
            out.append({
                "date": str(r["date"]),
                "ticker": tk,
                "catalyst_type": "SEC_8K",
                "title": f"8-K — {', '.join(labels)}",
                "impact": "High" if heavy else "Medium",
                "source": "SEC EDGAR",
                "items": items,
                "primary_doc": str(r.get("primary_doc") or ""),
                "accession_number": str(r.get("accession_number") or ""),
            })

    return out


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


@router.get("/api/catalysts/asof/{ticker}")
@router.get("/api/catalysts/snapshot/{ticker}", include_in_schema=False)
async def get_catalyst_snapshot(
    ticker: str,
    as_of: Optional[str] = Query(
        None, description="Point-in-time view date YYYY-MM-DD (default: today)"
    ),
    window_days: int = Query(
        7, description="Lookback window for news/SEC/insider events (default 7d)"
    ),
):
    """Unified point-in-time catalyst view for a ticker.

    Note on naming: the canonical path is /api/catalysts/asof/{ticker}.
    The /snapshot/ alias is preserved for back-compat — the word
    'snapshot' otherwise refers to the etf_options_snapshots table
    (live intraday options chain capture, currently paused), and they
    are unrelated.

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
