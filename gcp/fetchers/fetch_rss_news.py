#!/usr/bin/env python3
"""Fetch news from RSS feeds + FinViz, score with FinBERT + Gemini Flash.

5-step pipeline:
    1. COLLECT  — poll RSS feeds + FinViz ticker_news per watchlist ticker
    2. DEDUP    — by URL, keep the row with most fields filled
    3. MATCH    — identify watchlist tickers via SA tags / regex / aliases;
                  discard articles with zero matches
    4. FINBERT  — bulk sentiment on all matched articles (free, CPU)
    5. GEMINI   — top articles only (high relevance or multi-ticker) for
                  relationship-aware per-ticker scoring via Vertex AI

Usage:
    python -m gcp.fetchers.fetch_rss_news
    python -m gcp.fetchers.fetch_rss_news --dry-run
    python -m gcp.fetchers.fetch_rss_news --no-score       # skip all scoring
    python -m gcp.fetchers.fetch_rss_news --no-gemini      # FinBERT only
    python -m gcp.fetchers.fetch_rss_news --max-age-hours 6 # FinViz recency filter
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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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

RSS_FEEDS: list[tuple[str, str]] = [
    # (source_label, url)
    ("seeking_alpha",      "https://seekingalpha.com/market_currents.xml"),
    ("seeking_alpha",      "https://seekingalpha.com/tag/wall-st-breakfast.xml"),
    ("seeking_alpha",      "https://seekingalpha.com/tag/etf-portfolio-strategy.xml"),
    ("yahoo_finance",      "https://finance.yahoo.com/news/rssindex"),
    ("cnbc",               "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("cnbc",               "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
    ("cnbc",               "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
    ("cnbc",               "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("marketwatch",        "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("investing_com",      "https://www.investing.com/rss/news.rss"),
    ("investing_com",      "https://www.investing.com/rss/news_25.rss"),
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
NOISE_WORDS = {"US", "USA", "AI", "CEO", "CFO", "IPO", "ETF", "GDP", "FDA",
               "SEC", "NYSE", "PM", "AM", "EST", "UTC", "THE", "FOR", "AND",
               "CEO", "NEW", "BIG", "TOP", "ALL", "NOW", "KEY", "WAR"}

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


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: COLLECT
# ═══════════════════════════════════════════════════════════════════════════

def _parse_pub_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _fetch_rss(url: str) -> list[dict]:
    """Fetch one RSS feed, return list of article dicts."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            logger.warning("RSS %s returned HTTP %d", url, r.status_code)
            return []
        root = ET.fromstring(r.content)
    except Exception as exc:
        logger.warning("RSS fetch failed %s: %s", url, exc)
        return []

    articles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = HTML_TAG_RE.sub("", (item.findtext("description") or "")).strip()[:500]
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        cats = [c.text.strip() for c in item.findall("category") if c.text]
        if not title or not link:
            continue
        articles.append({
            "title": title,
            "description": desc,
            "url": link,
            "pub_date_raw": pub,
            "published_ts": _parse_pub_date(pub),
            "categories": cats,
        })
    return articles


def collect_all(watchlist: list[str], max_age_hours: int = 24) -> list[dict]:
    """Step 1: Collect articles from all RSS feeds + FinViz news."""
    all_articles: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    # RSS feeds
    for source_label, url in RSS_FEEDS:
        logger.info("Fetching RSS: %s", url.split("/")[2])
        articles = _fetch_rss(url)
        for a in articles:
            a["source"] = source_label
            a["data_source"] = "rss"
        all_articles.extend(articles)
        logger.info("  %d articles", len(articles))
        time.sleep(0.3)

    # FinViz per-ticker news
    for tk in watchlist:
        logger.info("Fetching FinViz news: %s", tk)
        fv_articles = get_finviz_news(tk)
        for a in fv_articles:
            pub_ts = _parse_pub_date(a.get("date", ""))
            all_articles.append({
                "title": a["title"],
                "description": "",
                "url": a.get("link", ""),
                "pub_date_raw": a.get("date", ""),
                "published_ts": pub_ts,
                "categories": [],
                "source": "finviz",
                "data_source": "finviz",
            })
        logger.info("  %d articles for %s", len(fv_articles), tk)

    # Filter by recency
    before = len(all_articles)
    all_articles = [
        a for a in all_articles
        if a.get("published_ts") is None or a["published_ts"] >= cutoff
    ]
    if len(all_articles) < before:
        logger.info("Filtered %d stale articles (>%dh old)", before - len(all_articles), max_age_hours)

    logger.info("Step 1 COLLECT: %d articles from %d sources", len(all_articles),
                len(set(a["source"] for a in all_articles)))
    return all_articles


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: DEDUP
# ═══════════════════════════════════════════════════════════════════════════

def dedup_articles(articles: list[dict]) -> list[dict]:
    """Step 2: Deduplicate by URL, keeping the row with most fields filled."""
    by_url: dict[str, dict] = {}
    for a in articles:
        url = a.get("url", "")
        if not url:
            continue
        existing = by_url.get(url)
        if existing is None:
            by_url[url] = a
        else:
            # Keep whichever has more non-empty fields
            new_score = sum(1 for v in a.values() if v)
            old_score = sum(1 for v in existing.values() if v)
            if new_score > old_score:
                by_url[url] = a

    result = list(by_url.values())
    logger.info("Step 2 DEDUP: %d → %d unique articles", len(articles), len(result))
    return result


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: MATCH
# ═══════════════════════════════════════════════════════════════════════════

# Hardcoded aliases for common ETFs/indices that AV OVERVIEW returns nothing for.
# These get added on top of whatever get_aliases() returns.
_ETF_ALIASES: dict[str, list[str]] = {
    "SPY":  ["S&P 500", "S&P500", "SPDR S&P", "S&P"],
    "QQQ":  ["Nasdaq 100", "Nasdaq-100", "Nasdaq 100 Trust", "QQQ Trust"],
    "IWM":  ["Russell 2000", "Russell-2000", "Russell 2K", "small-cap"],
    "DIA":  ["Dow Jones", "Dow 30", "Dow Industrials"],
    "SPX":  ["S&P 500 Index", "SPX Index", "S&P500 Index"],
    "VIX":  ["volatility index", "fear gauge"],
    "TLT":  ["20+ Year Treasury", "long-term Treasury"],
    "GLD":  ["gold ETF", "SPDR Gold"],
}


def _build_alias_map(tickers: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Build alias maps for ticker matching.

    Returns:
        (case_sensitive_map, case_insensitive_map)
        - case_sensitive_map: short tickers (≤4 chars) like SPY, QQQ — matched
          only when capitalized to avoid false positives ("spy story" → SPY)
        - case_insensitive_map: longer aliases like "Broadcom Inc" — case-
          insensitive match because company names appear in mixed case
    """
    case_sensitive: dict[str, str] = {}
    case_insensitive: dict[str, str] = {}

    for tk in tickers:
        # Bare ticker symbol — case-sensitive match only
        case_sensitive[tk] = tk

        # Company-name aliases from AV OVERVIEW
        for alias in get_aliases(tk):
            if alias == tk:
                continue
            # Names ≥5 chars are safe for case-insensitive matching
            if len(alias) >= 5:
                case_insensitive[alias.lower()] = tk
            else:
                case_sensitive[alias] = tk

        # Hardcoded ETF aliases
        for alias in _ETF_ALIASES.get(tk, []):
            if len(alias) >= 5:
                case_insensitive[alias.lower()] = tk
            else:
                case_sensitive[alias] = tk

    return case_sensitive, case_insensitive


def match_tickers(
    articles: list[dict],
    watchlist: list[str],
    case_sensitive_map: dict[str, str],
    case_insensitive_map: dict[str, str],
) -> list[dict]:
    """Step 3: Match watchlist tickers to articles. Returns matched rows.

    Each returned dict has all article fields plus:
        ticker, match_method, relevance_score
    One article can produce multiple rows (one per matched ticker).
    Articles with zero matches are discarded.

    Match priority (highest to lowest relevance):
        1. SA <category> tag         → direct, relevance=1.0
        2. Ticker symbol in title    → title_regex, relevance=0.9
        3. Ticker symbol in desc     → title_regex, relevance=0.5
        4. Company name in title     → alias_match, relevance=0.8
        5. Company name in desc      → alias_match, relevance=0.5
    """
    watchlist_set = set(watchlist)
    matched_rows: list[dict] = []

    for article in articles:
        matches: list[tuple[str, str, float]] = []  # (ticker, method, relevance)
        seen: set[str] = set()

        title = article.get("title", "")
        desc = article.get("description", "")

        # 1. SA category tags (direct match)
        for cat in article.get("categories", []):
            cat_up = cat.upper().strip()
            if cat_up in watchlist_set and cat_up not in seen:
                matches.append((cat_up, "direct", 1.0))
                seen.add(cat_up)

        # 2. Case-sensitive match for ticker symbols (e.g. SPY, QQQ, IWM)
        # Avoids false positives like "spy story" → SPY
        for alias, ticker in case_sensitive_map.items():
            if ticker in seen:
                continue
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, title):
                matches.append((ticker, "title_regex", 0.9))
                seen.add(ticker)
            elif re.search(pattern, desc):
                matches.append((ticker, "title_regex", 0.5))
                seen.add(ticker)

        # 3. Case-insensitive match for long company names (e.g. "Broadcom Inc")
        title_lower = title.lower()
        desc_lower = desc.lower()
        for alias_lower, ticker in case_insensitive_map.items():
            if ticker in seen:
                continue
            if alias_lower in title_lower:
                matches.append((ticker, "alias_match", 0.8))
                seen.add(ticker)
            elif alias_lower in desc_lower:
                matches.append((ticker, "alias_match", 0.5))
                seen.add(ticker)

        # Create one row per match
        for ticker, method, relevance in matches:
            row = {**article}
            row["ticker"] = ticker
            row["match_method"] = method
            row["relevance_score"] = relevance
            matched_rows.append(row)

    logger.info("Step 3 MATCH: %d articles → %d matched rows (%d tickers)",
                len(articles), len(matched_rows),
                len(set(r["ticker"] for r in matched_rows)))
    return matched_rows


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: FINBERT
# ═══════════════════════════════════════════════════════════════════════════

_finbert_pipeline = None


def _get_finbert():
    """Lazy-load FinBERT pipeline (440MB model, ~10s first load)."""
    global _finbert_pipeline
    if _finbert_pipeline is not None:
        return _finbert_pipeline
    try:
        from transformers import pipeline as hf_pipeline
        logger.info("Loading FinBERT model (first load downloads ~440MB)...")
        _finbert_pipeline = hf_pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            device=-1,  # CPU
        )
        logger.info("FinBERT loaded successfully")
        return _finbert_pipeline
    except Exception as exc:
        logger.warning(
            "FinBERT unavailable (%s) — sentiment scores will be NULL. "
            "Install: pip install transformers torch", exc,
        )
        return None


def _finbert_score(text: str) -> tuple[Optional[float], Optional[str]]:
    """Score text with FinBERT. Returns (score, label) or (None, None)."""
    pipe = _get_finbert()
    if pipe is None:
        return None, None
    try:
        result = pipe(text[:512])[0]  # FinBERT max 512 tokens
        raw_label = result["label"]   # 'positive', 'negative', 'neutral'
        confidence = result["score"]  # 0.0 to 1.0
        if raw_label == "positive":
            score = confidence
        elif raw_label == "negative":
            score = -confidence
        else:
            score = confidence * 0.05  # neutral → near zero
        return score, _score_to_label(score)
    except Exception as exc:
        logger.debug("FinBERT scoring failed: %s", exc)
        return None, None


def score_finbert(matched_rows: list[dict]) -> list[dict]:
    """Step 4: Score all matched rows with FinBERT."""
    pipe = _get_finbert()
    if pipe is None:
        logger.warning("Step 4 FINBERT: skipped (model unavailable)")
        return matched_rows

    # Batch by unique article URL (same article scored once)
    url_scores: dict[str, tuple[Optional[float], Optional[str]]] = {}
    unique_urls = list({r["url"] for r in matched_rows})
    url_to_text = {}
    for r in matched_rows:
        if r["url"] not in url_to_text:
            text = r["title"]
            if r.get("description"):
                text += ". " + r["description"]
            url_to_text[r["url"]] = text

    logger.info("Step 4 FINBERT: scoring %d unique articles...", len(unique_urls))
    scored = 0
    for url in unique_urls:
        text = url_to_text[url]
        score, label = _finbert_score(text)
        url_scores[url] = (score, label)
        scored += 1
        if scored % 25 == 0:
            logger.info("  scored %d/%d articles", scored, len(unique_urls))

    # Apply scores to all rows
    for row in matched_rows:
        score, label = url_scores.get(row["url"], (None, None))
        row["overall_sentiment_score"] = score
        row["overall_sentiment_label"] = label
        # Per-ticker sentiment = overall for now (FinBERT is article-level)
        row["sentiment_score"] = score

    logger.info("Step 4 FINBERT: scored %d articles, applied to %d rows", scored, len(matched_rows))
    return matched_rows


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: GEMINI (top articles only)
# ═══════════════════════════════════════════════════════════════════════════

_GEMINI_PROMPT = """\
You are a financial sentiment analyst. Score this news article's impact on specific tickers.

Article: {title}
Summary: {description}

Tickers to evaluate: {tickers}
Peer relationships: {peer_context}

For EACH ticker, provide:
- sentiment: float -1.0 (bearish) to +1.0 (bullish)
- relevance: float 0.0 to 1.0
- reason: 10 words max

Respond ONLY with valid JSON:
{{"ticker_scores": {{"TICK": {{"sentiment": 0.0, "relevance": 0.0, "reason": "..."}}}}}}
"""


def _get_gemini_client():
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
        logger.info("Gemini auth: service account key at %s", key_file)
    else:
        logger.info("Gemini auth: using Application Default Credentials")
    return genai.Client(vertexai=True, project=project, location=location, credentials=credentials)


def _score_gemini(client, title: str, desc: str, tickers: list[str], peer_map: dict) -> Optional[dict]:
    """Score one article with Gemini Flash. Returns {ticker: {sentiment, relevance, reason}} or None."""
    from google.genai import types

    peer_lines = [f"  {tk}: {', '.join(peer_map.get(tk, [])[:5])}" for tk in tickers if peer_map.get(tk)]
    prompt = _GEMINI_PROMPT.format(
        title=title[:200],
        description=desc[:400],
        tickers=", ".join(tickers),
        peer_context="\n".join(peer_lines) or "None",
    )
    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=256),
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or "ticker_scores" not in parsed:
            return None
        return parsed["ticker_scores"]
    except json.JSONDecodeError as exc:
        logger.debug("Gemini JSON parse failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Gemini scoring failed: %s", exc)
        return None


def score_gemini_top(
    matched_rows: list[dict],
    watchlist: list[str],
    peer_map: dict[str, list[str]],
    relevance_threshold: float = 0.7,
    max_calls: int = 20,
) -> list[dict]:
    """Step 5: Score top articles with Gemini Flash for relationship analysis.

    Only scores articles where:
      - relevance >= threshold (high-quality matches), OR
      - article matched 2+ watchlist tickers (multi-ticker)
    """
    # Find articles worth Gemini-scoring
    url_tickers: dict[str, set[str]] = {}
    url_max_rel: dict[str, float] = {}
    for row in matched_rows:
        url = row["url"]
        url_tickers.setdefault(url, set()).add(row["ticker"])
        url_max_rel[url] = max(url_max_rel.get(url, 0), row.get("relevance_score", 0))

    gemini_urls = set()
    for url, tickers in url_tickers.items():
        if url_max_rel.get(url, 0) >= relevance_threshold or len(tickers) >= 2:
            gemini_urls.add(url)

    if not gemini_urls:
        logger.info("Step 5 GEMINI: no articles qualify (threshold=%.1f)", relevance_threshold)
        return matched_rows

    # Cap at max_calls
    gemini_urls = set(list(gemini_urls)[:max_calls])
    logger.info("Step 5 GEMINI: scoring %d articles (of %d total)", len(gemini_urls), len(url_tickers))

    # Initialize client
    try:
        client = _get_gemini_client()
        # Test call
        from google.genai import types
        client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text="hi")])],
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        logger.info("Gemini Flash client verified")
    except Exception as exc:
        logger.warning("Gemini unavailable (%s) — skipping Step 5", exc)
        return matched_rows

    # Build URL → article text lookup
    url_text: dict[str, tuple[str, str]] = {}
    for row in matched_rows:
        if row["url"] not in url_text:
            url_text[row["url"]] = (row["title"], row.get("description", ""))

    # Score
    gemini_results: dict[str, dict] = {}  # url → {ticker: {sentiment, relevance, reason}}
    for i, url in enumerate(gemini_urls):
        title, desc = url_text[url]
        tickers_for_article = list(url_tickers[url])
        scores = _score_gemini(client, title, desc, tickers_for_article, peer_map)
        if scores:
            gemini_results[url] = scores
            # Check if Gemini found additional watchlist tickers via relationships
            for tk, sc in scores.items():
                tk = tk.upper()
                if tk in set(watchlist) and tk not in url_tickers[url]:
                    if sc.get("relevance", 0) > 0.2:
                        # Add a new row for the relationship-discovered ticker
                        base_row = next(r for r in matched_rows if r["url"] == url)
                        new_row = {**base_row}
                        new_row["ticker"] = tk
                        new_row["match_method"] = "relationship"
                        new_row["relevance_score"] = sc.get("relevance", 0.3)
                        new_row["sentiment_score"] = sc.get("sentiment")
                        matched_rows.append(new_row)
                        logger.debug("Gemini discovered %s via relationship in: %s", tk, title[:60])
        if (i + 1) % 5 == 0:
            logger.info("  Gemini scored %d/%d", i + 1, len(gemini_urls))

    # Overwrite FinBERT scores with Gemini scores where available
    for row in matched_rows:
        url_scores = gemini_results.get(row["url"])
        if url_scores:
            tk_score = url_scores.get(row["ticker"]) or url_scores.get(row["ticker"].upper())
            if tk_score:
                row["sentiment_score"] = tk_score.get("sentiment", row.get("sentiment_score"))
                if tk_score.get("relevance") is not None:
                    row["relevance_score"] = tk_score["relevance"]

    logger.info("Step 5 GEMINI: %d articles scored, %d relationship discoveries",
                len(gemini_results),
                sum(1 for r in matched_rows if r.get("match_method") == "relationship"))
    return matched_rows


# ═══════════════════════════════════════════════════════════════════════════
# STEP 6: WRITE
# ═══════════════════════════════════════════════════════════════════════════

def build_dataframe(matched_rows: list[dict]) -> pd.DataFrame:
    """Convert matched rows to a DataFrame aligned with news_sentiment schema."""
    records = []
    for row in matched_rows:
        records.append({
            "ticker": row["ticker"],
            "published_ts": row.get("published_ts") or datetime.now(timezone.utc),
            "title": row["title"][:500],
            "url": row["url"][:1000],
            "summary": row.get("description", "")[:2000] or None,
            "sentiment_score": row.get("sentiment_score"),
            "relevance_score": row.get("relevance_score"),
            "overall_sentiment_score": row.get("overall_sentiment_score"),
            "overall_sentiment_label": row.get("overall_sentiment_label"),
            "topics": row.get("categories") or None,
            "source": row.get("source", "unknown"),
            "data_source": row.get("data_source", "rss"),
            "match_method": row.get("match_method", "direct"),
        })
    df = pd.DataFrame(records)

    # Validate required columns
    required = ["ticker", "published_ts", "url"]
    for col in required:
        if col not in df.columns:
            logger.error("DataFrame missing required column: %s", col)
            return pd.DataFrame()

    # Drop rows with NULL conflict columns
    before = len(df)
    df = df.dropna(subset=required)
    if len(df) < before:
        logger.warning("Dropped %d rows with NULL required fields", before - len(df))

    return df


def write_to_cloud_sql(df: pd.DataFrame) -> int:
    """Step 6: Upsert DataFrame to news_sentiment table."""
    if df.empty:
        return 0
    try:
        from gcp.database import upsert_dataframe, is_cloud_sql_configured
        if not is_cloud_sql_configured():
            logger.warning(
                "Cloud SQL not configured — set CLOUD_SQL_CONNECTION_NAME, "
                "DB_USER, DB_PASS, DB_NAME env vars"
            )
            return 0
        n = upsert_dataframe(df, "news_sentiment", conflict_cols=["ticker", "published_ts", "url"])
        logger.info("Step 6 WRITE: upserted %d rows to news_sentiment", n)
        return n
    except Exception as exc:
        logger.error("Cloud SQL write failed (%d rows): %s", len(df), exc)
        return 0


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    setup_logging()
    parser = argparse.ArgumentParser(description="RSS + FinViz news → FinBERT + Gemini → news_sentiment")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Cloud SQL")
    parser.add_argument("--no-score", action="store_true", help="Skip all sentiment scoring")
    parser.add_argument("--no-gemini", action="store_true", help="Skip Gemini (FinBERT only)")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Discard articles older than N hours")
    parser.add_argument("--gemini-max", type=int, default=20, help="Max Gemini API calls per run")
    args = parser.parse_args()

    # Load watchlist
    try:
        from gcp.fetchers._watchlist import load_watchlist
        watchlist = load_watchlist()
    except ImportError:
        cfg_path = Path(__file__).resolve().parents[2] / "alert_config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            watchlist = [t.upper() for t in (data.get("watchlist") or [])]
        else:
            watchlist = []

    if not watchlist:
        logger.error("Watchlist empty — set alert_config.json watchlist or INSIGHT_TICKERS env var")
        return

    logger.info("Watchlist (%d): %s", len(watchlist), watchlist)

    # Check AV key
    if not os.environ.get("ALPHA_VANTAGE_API_KEY"):
        logger.warning("ALPHA_VANTAGE_API_KEY not set — alias matching will use cached data only")

    # Build alias maps (case-sensitive for tickers, case-insensitive for names)
    case_sensitive_map, case_insensitive_map = _build_alias_map(watchlist)
    logger.info("Alias map: %d ticker symbols (case-sensitive), %d names (case-insensitive)",
                len(case_sensitive_map), len(case_insensitive_map))

    peer_map: dict[str, list[str]] = {}
    for tk in watchlist:
        peers = get_peers(tk)
        if peers:
            peer_map[tk] = peers
            logger.info("  %s peers: %s", tk, peers[:5])

    # ── STEP 1: COLLECT ──
    articles = collect_all(watchlist, max_age_hours=args.max_age_hours)
    if not articles:
        logger.info("No articles collected")
        return

    # ── STEP 2: DEDUP ──
    articles = dedup_articles(articles)

    # ── STEP 3: MATCH ──
    matched_rows = match_tickers(articles, watchlist, case_sensitive_map, case_insensitive_map)
    if not matched_rows:
        logger.info("No articles matched watchlist tickers")
        return

    # ── STEP 4: FINBERT ──
    if not args.no_score:
        matched_rows = score_finbert(matched_rows)
    else:
        logger.info("Step 4 FINBERT: skipped (--no-score)")

    # ── STEP 5: GEMINI ──
    if not args.no_score and not args.no_gemini:
        matched_rows = score_gemini_top(matched_rows, watchlist, peer_map, max_calls=args.gemini_max)
    else:
        logger.info("Step 5 GEMINI: skipped")

    # ── STEP 6: WRITE ──
    df = build_dataframe(matched_rows)
    if df.empty:
        logger.info("No valid rows after validation")
        return

    # Display sample
    print(f"\n{'='*90}")
    print(f"  {len(df)} rows | {df['ticker'].nunique()} tickers | {df['source'].nunique()} sources")
    print(f"{'='*90}")
    for _, row in df.head(20).iterrows():
        s = f"{row['sentiment_score']:+.2f}" if pd.notna(row.get("sentiment_score")) else " NULL"
        r = f"{row['relevance_score']:.2f}" if pd.notna(row.get("relevance_score")) else " NULL"
        print(f"  {row['ticker']:6s} sent={s:>6s} rel={r:>5s} [{row['match_method']:12s}] {row['source']:15s} {str(row['title'])[:55]}")
    print()

    if args.dry_run:
        logger.info("DRY RUN — not writing to Cloud SQL")
        return

    write_to_cloud_sql(df)


if __name__ == "__main__":
    main()
