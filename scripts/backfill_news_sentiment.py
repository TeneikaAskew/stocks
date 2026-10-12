#!/usr/bin/env python3
"""Backfill news_sentiment from AlphaVantage NEWS_SENTIMENT endpoint.

AV returns up to 50 recent articles per ticker with overall_sentiment_score
(-1 to +1) and per-ticker relevance_score (0 to 1). We persist these into
the news_sentiment table so summarize_news_sentiment() has data to display.

Usage:
    python scripts/backfill_news_sentiment.py --tickers SPY,IWM,QQQ
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AV_URL = "https://www.alphavantage.co/query"


def parse_av_time(ts: str) -> datetime:
    # AV format: "20260414T073000"
    return datetime.strptime(ts, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def fetch_av_news(ticker: str, api_key: str, limit: int = 50) -> list[dict]:
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "limit": str(limit),
        "apikey": api_key,
    }
    r = requests.get(AV_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    from gcp.fetchers.fetch_news_sentiment import _safe_float
    feed = data.get("feed", [])
    out = []
    for item in feed:
        # Find per-ticker sentiment
        ticker_sent = None
        relevance = None
        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker", "").upper() == ticker.upper():
                ticker_sent = _safe_float(ts.get("ticker_sentiment_score"))
                relevance = _safe_float(ts.get("relevance_score"))
                break
        out.append(
            {
                "ticker": ticker.upper(),
                "published_ts": parse_av_time(item.get("time_published", "")),
                "title": item.get("title", "")[:500],
                "url": (item.get("url") or "")[:1000] or None,
                "summary": item.get("summary", "")[:2000] if item.get("summary") else None,
                "sentiment_score": ticker_sent,
                "relevance_score": relevance,
                "source": (item.get("source") or "AlphaVantage")[:100],
            }
        )
    return out


def prepare_news_rows(frame):
    from gcp.fetchers.fetch_news_sentiment import prepare_news_rows as prepare
    return prepare(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default="SPY,IWM,QQQ", help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=50, help="Max articles per ticker")
    args = parser.parse_args()

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY") or os.environ.get("AV_API_KEY")
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set")
        sys.exit(1)

    from gcp.database import upsert_dataframe

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    total_rows = 0
    for t in tickers:
        log.info("%s: fetching up to %d news articles from AlphaVantage", t, args.limit)
        try:
            rows = fetch_av_news(t, api_key, limit=args.limit)
        except Exception as e:
            log.error("%s: AV fetch failed error_class=%s", t, type(e).__name__)
            continue

        if not rows:
            log.warning("%s: no articles returned", t)
            continue

        df = pd.DataFrame(rows)
        from gcp.fetchers.fetch_news_sentiment import persist_to_cloud_sql
        n = persist_to_cloud_sql(prepare_news_rows(df))
        log.info("%s: wrote %d rows to news_sentiment", t, n)
        total_rows += n

    log.info("DONE: %d rows across %d tickers", total_rows, len(tickers))


if __name__ == "__main__":
    main()
