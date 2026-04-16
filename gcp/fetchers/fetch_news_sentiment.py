#!/usr/bin/env python3
"""
Fetch news sentiment data from AlphaVantage NEWS_SENTIMENT endpoint.

Polls for recent headlines related to the given tickers, extracts
per-ticker relevance and sentiment scores, and upserts to the
news_sentiment Cloud SQL table.

Scheduled by GitHub Actions every 4 hours on weekdays.

Usage:
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY,IWM,QQQ
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = "SPY,IWM,QQQ"
AV_BASE_URL = "https://www.alphavantage.co/query"


def fetch_news_for_ticker(ticker: str, api_key: str, limit: int = 50) -> pd.DataFrame:
    """Fetch NEWS_SENTIMENT for a single ticker from AlphaVantage.

    Returns a DataFrame matching the news_sentiment schema columns.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests library not available")
        return pd.DataFrame()

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper(),
        "limit": limit,
        "apikey": api_key,
    }

    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("AlphaVantage NEWS_SENTIMENT request failed for %s: %s", ticker, e)
        return pd.DataFrame()

    feed = data.get("feed", [])
    if not feed:
        logger.info("No news articles returned for %s", ticker)
        return pd.DataFrame()

    rows = []
    for article in feed:
        published = article.get("time_published", "")
        title = article.get("title", "")
        url = article.get("url", "")
        summary = article.get("summary", "")
        source = article.get("source", "")

        # Find the ticker-specific sentiment from the per-ticker list
        ticker_sentiments = article.get("ticker_sentiment", [])
        relevance = None
        sentiment = None
        for ts in ticker_sentiments:
            if ts.get("ticker", "").upper() == ticker.upper():
                relevance = _safe_float(ts.get("relevance_score"))
                sentiment = _safe_float(ts.get("ticker_sentiment_score"))
                break

        # Parse published timestamp (format: "20250416T120000")
        pub_ts = _parse_av_timestamp(published)
        if pub_ts is None:
            continue

        rows.append({
            "ticker": ticker.upper(),
            "published_ts": pub_ts,
            "title": (title[:500] if title else None),
            "url": (url[:1000] if url else None),
            "summary": (summary[:2000] if summary else None),
            "sentiment_score": sentiment,
            "relevance_score": relevance,
            "source": (source[:100] if source else None),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ticker", "published_ts", "url"], keep="last")
    logger.info("Fetched %d articles for %s", len(df), ticker)
    return df


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
        logger.info("No news sentiment rows to persist")
        return 0

    if not is_cloud_sql_configured():
        logger.warning("Cloud SQL not configured -- skipping persist")
        return 0

    n = upsert_dataframe(df, "news_sentiment", ["ticker", "published_ts", "url"])
    logger.info("Upserted %d rows to news_sentiment", n)
    return n


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Fetch news sentiment → Cloud SQL")
    parser.add_argument(
        "--tickers",
        type=str,
        default=os.environ.get("NEWS_TICKERS", DEFAULT_TICKERS),
        help="Comma-separated tickers (default: SPY,IWM,QQQ)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max articles per ticker (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print without writing to DB",
    )
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY")
    if not api_key:
        logger.error("AV_API_KEY not set — cannot fetch news sentiment")
        sys.exit(1)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        logger.error("No tickers specified")
        sys.exit(1)

    frames = []
    for ticker in tickers:
        df = fetch_news_for_ticker(ticker, api_key, limit=args.limit)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning("No news sentiment data fetched from any ticker")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ticker", "published_ts", "url"], keep="last"
    )
    logger.info("Total news rows: %d", len(combined))

    if args.dry_run:
        print(combined.to_string(index=False))
        print(f"\n[dry-run] {len(combined)} rows — not written to DB")
        return

    n = persist_to_cloud_sql(combined)
    print(f"Persisted {n} news sentiment rows to Cloud SQL")


if __name__ == "__main__":
    main()
