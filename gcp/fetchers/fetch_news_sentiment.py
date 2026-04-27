#!/usr/bin/env python3
"""
Fetch news sentiment data from AlphaVantage NEWS_SENTIMENT endpoint.

Two query modes (can be combined in one invocation):

* **ticker mode** (`--tickers SPY,IWM,QQQ`) — pulls articles tagged with
  the given tickers. Use for the always-on watchlist.

* **topic mode** (`--topics mergers_and_acquisitions,technology,...`) —
  pulls articles by AV catalyst topic regardless of ticker. Use to
  capture single-name catalysts (e.g. an AVGO/Google deal) for tickers
  outside the watchlist.

For each article returned by AV, we persist **one row per ticker** in
the article's `ticker_sentiment` array (not just the queried ticker),
plus the article's `topics` and `overall_sentiment_*`. That way an
article about SPY that also mentions AAPL/AVGO/GOOGL produces a row
for each, surfacing the catalyst signal for every name involved.

Usage:
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY,IWM,QQQ
    python -m gcp.fetchers.fetch_news_sentiment --topics mergers_and_acquisitions,technology
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY --topics earnings --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import (
    upsert_dataframe, is_cloud_sql_configured, query_to_dataframe,
)
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = "SPY,IWM,QQQ"
# Five catalyst-rich topics — AV's hard cap per call. Names match
# https://www.alphavantage.co/documentation/#news-sentiment
DEFAULT_TOPICS = (
    "mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences"
)
AV_BASE_URL = "https://www.alphavantage.co/query"

# Incremental-fetch tunables. The 30-min overlap catches edge articles
# whose timestamps got revised after first ingest (the upsert dedupes
# the overlap, so re-pulling is free). 48h cold-start window matches
# the brief's news lookback. 7d is the stale-ticker cap so a thinly-
# covered ticker doesn't trigger an unbounded historical pull.
SAFETY_OVERLAP_MINUTES = 30
COLD_START_LOOKBACK_HOURS = 48
MAX_INCREMENTAL_HOURS = 24 * 7


def _fetch(params: dict) -> list[dict]:
    """Issue a single NEWS_SENTIMENT call and return the raw `feed` list."""
    try:
        import requests
    except ImportError:
        logger.error("requests library not available")
        return []

    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("AV NEWS_SENTIMENT request failed (%s): %s", params, e)
        return []

    if "Information" in data:
        logger.warning("AV info: %s", data["Information"])
    return data.get("feed", []) or []


def _article_to_rows(article: dict) -> list[dict]:
    """Explode one article into one row per ticker mentioned.

    AV returns each article with a `ticker_sentiment` array listing every
    ticker the article touches plus per-ticker relevance/sentiment. We
    persist one row per (article, ticker) so a single AVGO/GOOGL article
    feeds the catalyst signal for both names.
    """
    pub_ts = _parse_av_timestamp(article.get("time_published", ""))
    if pub_ts is None:
        return []

    title = (article.get("title") or "")[:500] or None
    url = (article.get("url") or "")[:1000] or None
    summary = (article.get("summary") or "")[:2000] or None
    source = (article.get("source") or "")[:100] or None

    overall_score = _safe_float(article.get("overall_sentiment_score"))
    overall_label = (article.get("overall_sentiment_label") or "")[:20] or None

    # AV topics are objects: [{"topic": "Technology", "relevance_score": "0.5"}, ...]
    topics = [
        t["topic"]
        for t in (article.get("topics") or [])
        if isinstance(t, dict) and t.get("topic")
    ]

    ticker_entries = article.get("ticker_sentiment") or []
    if not ticker_entries:
        return []

    rows = []
    for ts in ticker_entries:
        tk = (ts.get("ticker") or "").upper().strip()
        if not tk:
            continue
        rows.append(
            {
                "ticker": tk,
                "published_ts": pub_ts,
                "title": title,
                "url": url,
                "summary": summary,
                "sentiment_score": _safe_float(ts.get("ticker_sentiment_score")),
                "relevance_score": _safe_float(ts.get("relevance_score")),
                "overall_sentiment_score": overall_score,
                "overall_sentiment_label": overall_label,
                "topics": topics or None,
                "source": source,
            }
        )
    return rows


def _last_published_ts(ticker: str) -> Optional[datetime]:
    """Most recent ``published_ts`` we have for this ticker, or ``None``
    on cold start / DB read failure.

    Used by the incremental fetch path so each scheduled run only asks
    AV for articles newer than what we already have. The DB query is
    a cheap MAX over the indexed (ticker, published_ts) tuple.

    Returns ``None`` (the cold-start signal) on any error so the caller
    falls back to the lookback-window default rather than crashing the
    fetch.
    """
    sql = "SELECT MAX(published_ts) AS max_ts FROM news_sentiment WHERE ticker = :tk"
    try:
        df = query_to_dataframe(sql, {"tk": ticker.upper()})
    except Exception:
        logger.warning("could not read MAX(published_ts) for %s; treating as cold start", ticker)
        return None
    if df.empty or df.iloc[0, 0] is None:
        return None
    val = df.iloc[0, 0]
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        return pd.to_datetime(val, utc=True).to_pydatetime()
    except Exception:
        return None


def _resolve_incremental_time_from(
    ticker: str,
    now: datetime,
    *,
    last_ts: Optional[datetime] = None,
) -> str:
    """Compute the AV ``time_from`` string for an incremental fetch.

    Three branches:

    1. **Cold start** — no rows for this ticker. Pull the last
       ``COLD_START_LOOKBACK_HOURS`` (48h, matches the brief's news
       window) instead of unlimited history. Prevents a new ticker
       addition from silently triggering a years-deep AV pull.

    2. **Stale ticker** — last article > ``MAX_INCREMENTAL_HOURS``
       (7d) ago. Cap at 7d so thinly-covered ETF/sector tickers
       don't ask AV for unbounded history every run.

    3. **Normal** — subtract ``SAFETY_OVERLAP_MINUTES`` from the
       last published_ts. The 30-min overlap catches edge articles
       whose timestamps got revised after first ingest; the upsert
       dedupes the overlap so re-pulling is free.

    Pass ``last_ts`` explicitly when a caller (or test) already has it
    cached, to skip the per-ticker DB read.
    """
    if last_ts is None:
        last_ts = _last_published_ts(ticker)

    if last_ts is None:
        floor = now - timedelta(hours=COLD_START_LOOKBACK_HOURS)
        reason = "cold-start"
    elif (now - last_ts) > timedelta(hours=MAX_INCREMENTAL_HOURS):
        floor = now - timedelta(hours=MAX_INCREMENTAL_HOURS)
        reason = "stale-cap"
    else:
        floor = last_ts - timedelta(minutes=SAFETY_OVERLAP_MINUTES)
        reason = "incremental"

    av_str = floor.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")
    logger.info("ticker %s incremental floor=%s (%s)", ticker, av_str, reason)
    return av_str


def fetch_by_tickers(
    tickers: list[str], api_key: str, limit: int,
    time_from: str | None = None, time_to: str | None = None,
    incremental: bool = False,
) -> pd.DataFrame:
    """Ticker-mode pull — one AV call per ticker, exploded across all
    tickers each article mentions.

    ``time_from`` / ``time_to`` accept AV's ``YYYYMMDDTHHMM`` format
    and let callers backfill historical news rather than only the
    most recent 50 articles.

    ``incremental=True`` resolves a per-ticker ``time_from`` from the
    last persisted ``published_ts`` (with a 30-min safety overlap)
    when the caller didn't pin a window. Cold-start tickers get a
    48h lookback; stale tickers cap at 7d. This makes the scheduled
    crons cheap enough to bump the cadence to hourly without burning
    AV quota on duplicate-pull bandwidth.
    """
    rows: list[dict] = []
    # Snap "now" once per batch so all tickers see the same clock.
    batch_now = datetime.now(timezone.utc) if incremental else None

    for tk in tickers:
        # Per-ticker time_from: explicit caller wins; otherwise resolve
        # incrementally if requested; otherwise leave unset (= "AV's latest").
        tk_time_from = time_from
        if incremental and not time_from and not time_to:
            tk_time_from = _resolve_incremental_time_from(tk, batch_now)

        params: dict[str, str | int] = {
            "function": "NEWS_SENTIMENT",
            "tickers": tk,
            "limit": limit,
            "apikey": api_key,
        }
        if tk_time_from:
            params["time_from"] = tk_time_from
        if time_to:
            params["time_to"] = time_to
        if tk_time_from or time_to:
            params["sort"] = "EARLIEST"
        feed = _fetch(params)
        if not feed:
            logger.info("no articles for ticker %s", tk)
            continue
        article_rows: list[dict] = []
        for article in feed:
            article_rows.extend(_article_to_rows(article))
        logger.info(
            "ticker %s: %d articles → %d (article, ticker) rows",
            tk,
            len(feed),
            len(article_rows),
        )
        rows.extend(article_rows)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_by_topics(topics: list[str], api_key: str, limit: int) -> pd.DataFrame:
    """Topic-mode pull — one AV call covering up to 5 topics, exploded
    across all tickers each article mentions."""
    if len(topics) > 5:
        logger.warning(
            "AV NEWS_SENTIMENT accepts max 5 topics; truncating %d → 5",
            len(topics),
        )
        topics = topics[:5]
    feed = _fetch(
        {
            "function": "NEWS_SENTIMENT",
            "topics": ",".join(topics),
            "limit": limit,
            "apikey": api_key,
        }
    )
    if not feed:
        logger.info("no articles for topics %s", topics)
        return pd.DataFrame()
    rows: list[dict] = []
    for article in feed:
        rows.extend(_article_to_rows(article))
    logger.info(
        "topics %s: %d articles → %d (article, ticker) rows",
        topics,
        len(feed),
        len(rows),
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_av_timestamp(ts_str: str) -> datetime | None:
    """Parse AlphaVantage timestamp format '20250416T120000' to datetime."""
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except ValueError:
            logger.debug("unparseable timestamp: %s", ts_str)
            return None


def persist_to_cloud_sql(df: pd.DataFrame) -> int:
    """Upsert news sentiment rows to Cloud SQL."""
    if df.empty:
        logger.info("no rows to persist")
        return 0
    if not is_cloud_sql_configured():
        logger.warning("Cloud SQL not configured — skipping persist")
        return 0
    n = upsert_dataframe(df, "news_sentiment", ["ticker", "published_ts", "url"])
    logger.info("upserted %d rows to news_sentiment", n)
    return n


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Fetch news sentiment → Cloud SQL")
    parser.add_argument(
        "--tickers",
        type=str,
        default=os.environ.get("NEWS_TICKERS", ""),
        help="Comma-separated tickers for ticker-mode fetch.",
    )
    parser.add_argument(
        "--topics",
        type=str,
        default=os.environ.get("NEWS_TOPICS", ""),
        help="Comma-separated AV topics for topic-mode fetch (max 5).",
    )
    parser.add_argument("--limit", type=int, default=200,
                        help="Max articles per AV call (default: 200)")
    parser.add_argument(
        "--time-from", default=None,
        help="Backfill: AV time_from filter, format YYYYMMDDTHHMM (e.g. 20260407T0000)",
    )
    parser.add_argument(
        "--time-to", default=None,
        help="Backfill: AV time_to filter, format YYYYMMDDTHHMM",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print without writing to DB")
    parser.add_argument(
        "--since-last", action="store_true",
        default=os.environ.get("NEWS_SINCE_LAST", "").lower() in ("1", "true", "yes"),
        help=(
            "Per-ticker incremental fetch: AV time_from = last persisted "
            "published_ts minus 30-min safety overlap. Cold-start tickers "
            "fall back to a 48h lookback; stale tickers cap at 7d. Cuts "
            "scheduled-run bandwidth by ~99%% (no quota benefit, just less "
            "wasted parsing of articles the upsert already deduped). "
            "Ignored when --time-from or --time-to is passed (backfills "
            "always honour the explicit caller window)."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        logger.error("AV_API_KEY not set — cannot fetch news sentiment")
        sys.exit(1)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    topics = [t.strip().lower() for t in args.topics.split(",") if t.strip()]

    # If neither mode specified, fall back to the curated watchlist
    # (alert_config.json → "watchlist"), then DEFAULT_TICKERS.
    if not tickers and not topics:
        from gcp.fetchers._watchlist import load_watchlist
        wl = load_watchlist()
        tickers = wl or [t.strip().upper() for t in DEFAULT_TICKERS.split(",") if t.strip()]
        logger.info("no --tickers or --topics provided; defaulting to %s", tickers)

    frames: list[pd.DataFrame] = []
    if tickers:
        df = fetch_by_tickers(
            tickers, api_key, limit=args.limit,
            time_from=args.time_from, time_to=args.time_to,
            incremental=args.since_last,
        )
        if not df.empty:
            frames.append(df)
    if topics:
        df = fetch_by_topics(topics, api_key, limit=args.limit)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning("no news data fetched from any source")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ticker", "published_ts", "url"], keep="last"
    )
    logger.info("total rows after dedup: %d", len(combined))

    if args.dry_run:
        # topics column is a list — print compactly
        with pd.option_context("display.max_colwidth", 60):
            print(combined.to_string(index=False))
        print(f"\n[dry-run] {len(combined)} rows — not written to DB")
        return

    n = persist_to_cloud_sql(combined)
    print(f"Persisted {n} news sentiment rows to Cloud SQL")


if __name__ == "__main__":
    main()
