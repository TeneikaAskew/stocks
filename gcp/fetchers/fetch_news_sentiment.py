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

Backfill:
    Pass `--time-from` / `--time-to` (AV format: YYYYMMDDTHHMM, e.g.
    `20260406T0000`) to pull historical news. The 1000-row default
    `--limit` matches AV's documented ceiling — keep it at 1000 for
    backfills covering multi-day windows or you'll silently under-
    sample high-volume catalysts (the 4/6–4/11 AVGO backfill ran
    with limit=200 originally and missed 134 of 151 articles AV had).
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
# Five catalyst-rich topics — AV's hard cap per call. Names match
# https://www.alphavantage.co/documentation/#news-sentiment
DEFAULT_TOPICS = (
    "mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences"
)
AV_BASE_URL = "https://www.alphavantage.co/query"


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


def fetch_by_tickers(
    tickers: list[str], api_key: str, limit: int,
    time_from: str | None = None, time_to: str | None = None,
) -> pd.DataFrame:
    """Ticker-mode pull — one AV call per ticker, exploded across all
    tickers each article mentions.

    `time_from` / `time_to` accept AV's `YYYYMMDDTHHMM` format and let
    callers backfill historical news rather than only the most recent
    50 articles.
    """
    rows: list[dict] = []
    for tk in tickers:
        params: dict[str, str | int] = {
            "function": "NEWS_SENTIMENT",
            "tickers": tk,
            "limit": limit,
            "apikey": api_key,
        }
        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to
        if time_from or time_to:
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
    parser.add_argument("--limit", type=int, default=1000,
                        help=(
                            "Max articles per AV call (default: 1000, AV's documented ceiling). "
                            "The previous default of 200 caused silent under-coverage on high-volume "
                            "tickers — the 4/6–4/11 backfill window persisted only 17 of 151 AVGO "
                            "articles AV had available because every batch hit the cap."
                        ))
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
