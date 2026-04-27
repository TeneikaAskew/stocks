#!/usr/bin/env python3
"""Fetch news from RSS feeds + FinViz and score with Gemini Flash.

Polls RSS feeds (Seeking Alpha, Yahoo Finance, CNBC, MarketWatch,
Investing.com) and FinViz ticker news, deduplicates by URL, scores
sentiment via Vertex AI Gemini Flash, and writes rows to the
``news_sentiment`` table in Cloud SQL.

Gemini Flash provides:
    - overall_sentiment_score (-1.0 to 1.0)
    - overall_sentiment_label (Bearish/Neutral/Bullish)
    - per-ticker sentiment + relevance (using peer context)

Usage:
    python -m gcp.fetchers.fetch_rss_news
    python -m gcp.fetchers.fetch_rss_news --dry-run
    python -m gcp.fetchers.fetch_rss_news --no-score   # skip Gemini, NULL sentiment
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.logging_config import setup_logging
from lib.ticker_info import get_aliases, get_peers, get_finviz_news

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS feed definitions
# ---------------------------------------------------------------------------

RSS_FEEDS: list[tuple[str, str, str]] = [
    # (label, url, data_source_tag)
    ("sa_market_currents", "https://seekingalpha.com/market_currents.xml", "rss"),
    ("sa_wall_st_breakfast", "https://seekingalpha.com/tag/wall-st-breakfast.xml", "rss"),
    ("sa_etf_strategy", "https://seekingalpha.com/tag/etf-portfolio-strategy.xml", "rss"),
    ("yahoo_general", "https://finance.yahoo.com/news/rssindex", "rss"),
    ("cnbc_top_news", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "rss"),
    ("cnbc_investing", "https://www.cnbc.com/id/15839069/device/rss/rss.html", "rss"),
    ("cnbc_earnings", "https://www.cnbc.com/id/15839135/device/rss/rss.html", "rss"),
    ("cnbc_economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "rss"),
    ("marketwatch_top", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "rss"),
    ("investing_com_all", "https://www.investing.com/rss/news.rss", "rss"),
    ("investing_com_stock", "https://www.investing.com/rss/news_25.rss", "rss"),
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
NOISE_TICKERS = {"US", "USA", "AI", "CEO", "CFO", "IPO", "ETF", "GDP", "FDA",
                 "SEC", "NYSE", "PM", "AM", "EST", "UTC", "THE", "FOR", "AND"}

# Gemini sentiment label buckets (matching AV's convention)
LABEL_THRESHOLDS = [
    (-0.35, "Bearish"),
    (-0.15, "Somewhat-Bearish"),
    (0.15, "Neutral"),
    (0.35, "Somewhat-Bullish"),
    (float("inf"), "Bullish"),
]


def _score_to_label(score: float) -> str:
    for threshold, label in LABEL_THRESHOLDS:
        if score <= threshold:
            return label
    return "Bullish"


# ---------------------------------------------------------------------------
# Load watchlist + peer context
# ---------------------------------------------------------------------------

def _load_watchlist() -> list[str]:
    try:
        from gcp.fetchers._watchlist import load_watchlist
        return load_watchlist()
    except ImportError:
        cfg_path = Path(__file__).resolve().parents[2] / "alert_config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return [t.upper() for t in (data.get("watchlist") or [])]
    return []


def _build_alias_map(tickers: list[str]) -> dict[str, str]:
    """Build {alias_lower: TICKER} mapping for all watchlist tickers."""
    alias_map: dict[str, str] = {}
    for tk in tickers:
        for alias in get_aliases(tk):
            alias_map[alias.lower()] = tk
    return alias_map


def _build_peer_map(tickers: list[str]) -> dict[str, list[str]]:
    """Build {TICKER: [peers]} for all watchlist tickers."""
    peer_map: dict[str, list[str]] = {}
    for tk in tickers:
        peers = get_peers(tk)
        if peers:
            peer_map[tk] = peers
    return peer_map


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------

def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed, returning raw article dicts."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            logger.warning("RSS %s returned %d", url, r.status_code)
            return []
        root = ET.fromstring(r.content)
    except Exception as exc:
        logger.warning("RSS fetch failed %s: %s", url, exc)
        return []

    articles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc_raw = (item.findtext("description") or "").strip()
        desc = HTML_TAG_RE.sub("", desc_raw).strip()[:500]
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        categories = [c.text.strip() for c in item.findall("category") if c.text]

        if not title or not link:
            continue

        articles.append({
            "title": title,
            "description": desc,
            "url": link,
            "pub_date": pub,
            "categories": categories,
        })
    return articles


def _parse_pub_date(raw: str) -> Optional[datetime]:
    """Parse various RSS date formats to UTC datetime."""
    from email.utils import parsedate_to_datetime
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        pass
    # Try ISO format
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.debug("Unparseable date: %s", raw)
    return None


# ---------------------------------------------------------------------------
# Ticker matching
# ---------------------------------------------------------------------------

def _match_tickers_from_categories(categories: list[str], watchlist: set[str]) -> list[tuple[str, str]]:
    """Extract tickers from SA-style <category> tags. Returns [(ticker, method)]."""
    matches = []
    for cat in categories:
        cat_upper = cat.upper().strip()
        if cat_upper in watchlist:
            matches.append((cat_upper, "direct"))
        elif re.match(r"^[A-Z.]{1,6}$", cat_upper) and cat_upper not in NOISE_TICKERS:
            # Valid ticker format but not on watchlist — skip
            pass
    return matches


def _match_tickers_from_text(text: str, alias_map: dict[str, str]) -> list[tuple[str, str]]:
    """Match watchlist tickers from article text using aliases. Returns [(ticker, method)]."""
    matches = []
    seen = set()
    text_lower = text.lower()

    # Check each alias against text
    for alias_lower, ticker in alias_map.items():
        if ticker in seen:
            continue
        if len(alias_lower) <= 4:
            # Short aliases (ticker symbols) — need word boundary
            if re.search(r"\b" + re.escape(alias_lower) + r"\b", text_lower):
                matches.append((ticker, "title_regex"))
                seen.add(ticker)
        else:
            # Longer aliases (company names) — substring match is fine
            if alias_lower in text_lower:
                matches.append((ticker, "alias_match"))
                seen.add(ticker)

    return matches


# ---------------------------------------------------------------------------
# Gemini Flash scoring
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """Get a Gemini client using the project's Vertex AI setup.

    Credential resolution:
      1. GOOGLE_APPLICATION_CREDENTIALS env var → service account key file
      2. .gcp-key.json in repo root → local dev key file
      3. Application Default Credentials → Cloud Run service account
    """
    from google import genai
    project = os.environ.get("GCP_PROJECT_ID", "adept-mountain-474619-d4")
    location = os.environ.get("GCP_REGION", "us-east1")

    key_file = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path(__file__).resolve().parents[2] / ".gcp-key.json"),
    )
    credentials = None
    if key_file and Path(key_file).exists():
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            key_file, scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        logger.info("Gemini auth: using service account key at %s", key_file)
    else:
        logger.info(
            "Gemini auth: no key file at %s — falling back to Application Default Credentials "
            "(works on Cloud Run, may fail locally — run 'gcloud auth application-default login')",
            key_file,
        )

    return genai.Client(
        vertexai=True, project=project, location=location, credentials=credentials,
    )


_SCORE_PROMPT = """\
You are a financial sentiment analyst. Score the sentiment of this news article.

Article title: {title}
Article summary: {description}

Watchlist tickers to evaluate: {tickers}
Peer context: {peer_context}

For EACH watchlist ticker that this article is relevant to, provide:
- sentiment_score: float from -1.0 (very bearish) to +1.0 (very bullish)
- relevance_score: float from 0.0 (not relevant) to 1.0 (directly about this ticker)
- reason: brief explanation (10 words max)

Also provide an overall_sentiment_score for the article as a whole.

Respond in this exact JSON format, nothing else:
{{
  "overall_sentiment_score": 0.0,
  "ticker_scores": {{
    "TICKER": {{"sentiment": 0.0, "relevance": 0.0, "reason": "..."}},
  }}
}}

Only include tickers that have relevance > 0.1. If no watchlist tickers are relevant, return empty ticker_scores.
"""


def _score_article_gemini(
    client,
    title: str,
    description: str,
    watchlist: list[str],
    peer_map: dict[str, list[str]],
) -> Optional[dict]:
    """Score an article using Gemini Flash. Returns parsed JSON or None."""
    from google.genai import types

    peer_lines = []
    for tk in watchlist:
        peers = peer_map.get(tk, [])
        if peers:
            peer_lines.append(f"  {tk} peers: {', '.join(peers[:5])}")
    peer_context = "\n".join(peer_lines) if peer_lines else "No peer data available."

    prompt = _SCORE_PROMPT.format(
        title=title[:200],
        description=description[:400],
        tickers=", ".join(watchlist),
        peer_context=peer_context,
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
            ),
        )
        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)

        # Validate response structure
        if not isinstance(parsed, dict):
            logger.warning("Gemini returned non-dict: %s", type(parsed))
            return None
        if "overall_sentiment_score" not in parsed:
            logger.warning("Gemini response missing overall_sentiment_score")
            return None
        score = parsed["overall_sentiment_score"]
        if not isinstance(score, (int, float)) or score < -1.0 or score > 1.0:
            logger.warning("Gemini overall_sentiment_score out of range: %s", score)
            parsed["overall_sentiment_score"] = max(-1.0, min(1.0, float(score)))

        # Validate ticker_scores
        ts = parsed.get("ticker_scores", {})
        if not isinstance(ts, dict):
            parsed["ticker_scores"] = {}

        return parsed
    except json.JSONDecodeError as exc:
        logger.warning("Gemini returned invalid JSON: %s — raw: %s", exc, text[:200])
        return None
    except Exception as exc:
        logger.warning("Gemini scoring failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Article → news_sentiment rows
# ---------------------------------------------------------------------------

def _article_to_rows(
    article: dict,
    source_label: str,
    data_source: str,
    watchlist: list[str],
    watchlist_set: set[str],
    alias_map: dict[str, str],
    gemini_scores: Optional[dict],
) -> list[dict]:
    """Convert one article to news_sentiment rows (one per matched ticker)."""
    pub_ts = _parse_pub_date(article["pub_date"])
    if pub_ts is None:
        pub_ts = datetime.now(timezone.utc)

    # Determine matched tickers
    matched: list[tuple[str, str]] = []  # (ticker, method)

    # 1. SA category tags (direct)
    matched.extend(_match_tickers_from_categories(article.get("categories", []), watchlist_set))

    # 2. Title + description text matching
    text = article["title"] + " " + article.get("description", "")
    matched.extend(_match_tickers_from_text(text, alias_map))

    # 3. Gemini-identified tickers (relationship-based)
    if gemini_scores:
        ticker_scores = gemini_scores.get("ticker_scores", {})
        for tk, scores in ticker_scores.items():
            tk = tk.upper()
            if tk in watchlist_set and not any(m[0] == tk for m in matched):
                if scores.get("relevance", 0) > 0.1:
                    matched.append((tk, "relationship"))

    # Dedupe
    seen = set()
    unique_matched = []
    for tk, method in matched:
        if tk not in seen:
            seen.add(tk)
            unique_matched.append((tk, method))

    if not unique_matched:
        return []

    overall_score = None
    overall_label = None
    if gemini_scores:
        overall_score = gemini_scores.get("overall_sentiment_score")
        if overall_score is not None:
            overall_label = _score_to_label(overall_score)

    rows = []
    for ticker, method in unique_matched:
        sentiment_score = None
        relevance_score = None

        if gemini_scores:
            ts = gemini_scores.get("ticker_scores", {}).get(ticker, {})
            sentiment_score = ts.get("sentiment")
            relevance_score = ts.get("relevance")

        # Heuristic relevance if Gemini didn't score this ticker
        if relevance_score is None:
            if method == "direct":
                relevance_score = 1.0
            elif method == "title_regex":
                relevance_score = 0.9
            elif method == "alias_match":
                relevance_score = 0.7
            elif method == "relationship":
                relevance_score = 0.4

        rows.append({
            "ticker": ticker,
            "published_ts": pub_ts,
            "title": article["title"][:500],
            "url": article["url"][:1000],
            "summary": article.get("description", "")[:2000] or None,
            "sentiment_score": sentiment_score,
            "relevance_score": relevance_score,
            "overall_sentiment_score": overall_score,
            "overall_sentiment_label": overall_label,
            "topics": article.get("categories") or None,
            "source": source_label,
            "data_source": data_source,
            "match_method": method,
        })

    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def fetch_all_news(
    watchlist: list[str],
    alias_map: dict[str, str],
    peer_map: dict[str, list[str]],
    score: bool = True,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Fetch from all sources, score, and return a DataFrame of news_sentiment rows."""
    watchlist_set = set(watchlist)
    all_rows: list[dict] = []
    seen_urls: set[str] = set()

    # Get Gemini client if scoring — test with a small call first
    gemini_client = None
    if score:
        try:
            gemini_client = _get_gemini_client()
            # Test the client with a trivial call to catch auth errors early
            from google.genai import types
            gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[types.Content(role="user", parts=[types.Part(text="hi")])],
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            logger.info("Gemini Flash client initialized and verified")
        except Exception as exc:
            logger.warning("Gemini unavailable (%s), scoring disabled — rows will have NULL sentiment", exc)
            gemini_client = None
            score = False

    # 1. RSS feeds
    for label, url, ds in RSS_FEEDS:
        logger.info("Fetching RSS: %s", label)
        articles = _fetch_rss(url)
        logger.info("  %d articles from %s", len(articles), label)

        for article in articles:
            if article["url"] in seen_urls:
                continue
            seen_urls.add(article["url"])

            # Score with Gemini
            gemini_scores = None
            if score and gemini_client:
                gemini_scores = _score_article_gemini(
                    gemini_client,
                    article["title"],
                    article.get("description", ""),
                    watchlist,
                    peer_map,
                )

            rows = _article_to_rows(
                article, label, ds, watchlist, watchlist_set, alias_map, gemini_scores,
            )
            all_rows.extend(rows)

        time.sleep(0.5)

    # 2. FinViz news per watchlist ticker
    for tk in watchlist:
        logger.info("Fetching FinViz news: %s", tk)
        articles = get_finviz_news(tk)
        logger.info("  %d articles for %s", len(articles), tk)

        for article in articles:
            url = article.get("link", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            art_dict = {
                "title": article["title"],
                "description": "",
                "url": url,
                "pub_date": article.get("date", ""),
                "categories": [],
            }

            gemini_scores = None
            if score and gemini_client:
                gemini_scores = _score_article_gemini(
                    gemini_client,
                    article["title"],
                    "",
                    watchlist,
                    peer_map,
                )

            rows = _article_to_rows(
                art_dict, "finviz", "finviz", watchlist, watchlist_set, alias_map, gemini_scores,
            )
            all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    logger.info("Total rows: %d from %d unique articles", len(df), len(seen_urls))
    return df


def main():
    # Load .env if present (local dev)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    setup_logging()
    parser = argparse.ArgumentParser(description="Fetch RSS + FinViz news with Gemini scoring")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Cloud SQL")
    parser.add_argument("--no-score", action="store_true", help="Skip Gemini scoring (NULL sentiment)")
    parser.add_argument("--limit", type=int, default=0, help="Limit total articles processed (0=unlimited)")
    args = parser.parse_args()

    watchlist = _load_watchlist()
    if not watchlist:
        logger.error(
            "Watchlist is empty — check alert_config.json 'watchlist' array "
            "or set INSIGHT_TICKERS env var (comma-separated)"
        )
        return

    logger.info("Watchlist (%d tickers): %s", len(watchlist), watchlist)

    # Check AV key (needed for alias resolution)
    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not av_key:
        logger.warning(
            "ALPHA_VANTAGE_API_KEY not set — alias resolution will use cached data only. "
            "Set it in .env or fetch from GCP: "
            "gcloud secrets versions access latest --secret=av-api-key"
        )

    # Build context
    alias_map = _build_alias_map(watchlist)
    logger.info("Alias map: %d entries (ticker symbols + company name variants)", len(alias_map))
    for alias, tk in sorted(alias_map.items()):
        logger.debug("  '%s' → %s", alias, tk)

    peer_map = _build_peer_map(watchlist)
    for tk, peers in peer_map.items():
        logger.info("  %s peers: %s", tk, peers[:5])

    # Fetch and score
    df = fetch_all_news(
        watchlist, alias_map, peer_map,
        score=not args.no_score,
        dry_run=args.dry_run,
    )

    if df.empty:
        logger.info("No news matched watchlist tickers")
        return

    # Display sample
    print(f"\n{'='*80}")
    print(f"  {len(df)} rows for {df['ticker'].nunique()} tickers from {df['source'].nunique()} sources")
    print(f"{'='*80}")
    for _, row in df.head(15).iterrows():
        score_str = f"{row['sentiment_score']:+.2f}" if pd.notna(row.get("sentiment_score")) else "NULL"
        rel_str = f"{row['relevance_score']:.2f}" if pd.notna(row.get("relevance_score")) else "NULL"
        print(f"  {row['ticker']:6s} sent={score_str:>6s} rel={rel_str:>5s} [{row['match_method']:12s}] {row['source']:20s} {row['title'][:60]}")

    if args.dry_run:
        logger.info("DRY RUN — not writing to Cloud SQL")
        return

    # Validate DataFrame before write
    required_cols = ["ticker", "published_ts", "url", "title", "source", "data_source", "match_method"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.error("DataFrame missing required columns: %s — aborting write", missing)
        return

    # Drop rows with NULL conflict columns (would fail on upsert)
    before = len(df)
    df = df.dropna(subset=["ticker", "published_ts", "url"])
    if len(df) < before:
        logger.warning("Dropped %d rows with NULL ticker/published_ts/url", before - len(df))

    if df.empty:
        logger.info("No valid rows to write after validation")
        return

    # Write to Cloud SQL
    try:
        from gcp.database import upsert_dataframe, is_cloud_sql_configured
        if not is_cloud_sql_configured():
            logger.warning(
                "Cloud SQL not configured — skipping write. "
                "Set CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME env vars."
            )
            return
        n = upsert_dataframe(
            df, "news_sentiment",
            conflict_cols=["ticker", "published_ts", "url"],
        )
        logger.info("Upserted %d rows to news_sentiment", n)
    except Exception as exc:
        logger.error(
            "Cloud SQL write failed (%d rows, %d tickers): %s",
            len(df), df["ticker"].nunique(), exc,
        )


if __name__ == "__main__":
    main()
