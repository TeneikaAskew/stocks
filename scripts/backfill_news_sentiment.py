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
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AV_URL = "https://www.alphavantage.co/query"


def parse_av_time(ts: str) -> datetime:
    # AV format: "20260414T073000"
    return datetime.strptime(ts, "%Y%m%dT%H%M%S")


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
    feed = data.get("feed", [])
    out = []
    for item in feed:
        # Find per-ticker sentiment
        ticker_sent = 0.0
        relevance = 0.0
        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker", "").upper() == ticker.upper():
                ticker_sent = float(ts.get("ticker_sentiment_score", 0.0) or 0.0)
                relevance = float(ts.get("relevance_score", 0.0) or 0.0)
                break
        out.append(
            {
                "ticker": ticker.upper(),
                "published_ts": parse_av_time(item.get("time_published", "")),
                "title": item.get("title", "")[:500],
                "url": item.get("url", "")[:500],
                "summary": item.get("summary", "")[:2000] if item.get("summary") else None,
                "sentiment_score": ticker_sent,
                "relevance_score": relevance,
                "source": (item.get("source") or "AlphaVantage")[:100],
            }
        )
    return out


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
            log.error("%s: AV fetch failed: %s", t, e)
            continue

        if not rows:
            log.warning("%s: no articles returned", t)
            continue

        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["ticker", "published_ts", "url"])
        n = upsert_dataframe(df, "news_sentiment", ["ticker", "published_ts", "url"])
        log.info("%s: wrote %d rows to news_sentiment", t, n)
        total_rows += n

    log.info("DONE: %d rows across %d tickers", total_rows, len(tickers))


if __name__ == "__main__":
    main()
