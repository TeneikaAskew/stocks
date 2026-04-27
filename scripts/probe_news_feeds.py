#!/usr/bin/env python3
"""Probe candidate RSS news feeds and classify general vs ticker-specific.

Run locally (sandbox blocks outbound HTTP):

    python scripts/probe_news_feeds.py

Reports per feed:
  - HTTP status, content-type, byte size
  - <item> count, sample titles, pub dates (freshness)
  - Distinct $TICKER cashtags + (TKR) parens detected across titles
  - Heuristic class:
      PER_TICKER  if URL templates a ticker
      GENERAL     if URL has no ticker template (broad news feed)
  - Whether the feed exposes any of: <category>, <dc:subject>, <media:keywords>

Does not write anywhere. No API key needed.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from xml.etree import ElementTree as ET

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

FEEDS: list[tuple[str, str]] = [
    # --- Seeking Alpha ---
    ("SA market currents",            "https://seekingalpha.com/market_currents.xml"),
    ("SA per-ticker AVGO",            "https://seekingalpha.com/api/sa/combined/AVGO.xml"),
    ("SA Wall St Breakfast",          "https://seekingalpha.com/tag/wall-st-breakfast.xml"),
    ("SA ETF strategy",               "https://seekingalpha.com/tag/etf-portfolio-strategy.xml"),
    # --- Yahoo Finance ---
    ("Yahoo per-ticker AVGO",         "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AVGO&region=US&lang=en-US"),
    ("Yahoo general news",            "https://finance.yahoo.com/news/rssindex"),
    # --- CNBC ---
    ("CNBC top news",                 "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC markets/investing",        "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
    ("CNBC earnings",                 "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
    ("CNBC economy",                  "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("CNBC finance",                  "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    # --- MarketWatch (Dow Jones CDN) ---
    ("MarketWatch top stories",       "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch MarketPulse",       "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("MarketWatch real-time",         "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    # --- Investing.com ---
    ("Investing.com all news",        "https://www.investing.com/rss/news.rss"),
    ("Investing.com economy",         "https://www.investing.com/rss/news_14.rss"),
    ("Investing.com stock market",    "https://www.investing.com/rss/news_25.rss"),
    ("Investing.com market overview", "https://www.investing.com/rss/market_overview.rss"),
    # --- NASDAQ ---
    ("NASDAQ trade halts",            "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"),
]

URL_TICKER_RE   = re.compile(r"[?&/](?:s=|combined/)([A-Z]{1,5})(?:\.xml|$|&)")
PARENS_TICKER   = re.compile(r"\(([A-Z]{1,5})(?::[A-Z]+)?\)")
CASHTAG_TICKER  = re.compile(r"\$([A-Z]{1,5})\b")
NS = {
    "dc":    "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}


def fetch(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", e.read() or b""
    except Exception as e:
        return 0, f"error: {e}", b""


def classify(url: str, body: bytes) -> dict:
    out = {
        "items": 0, "tickers": set(), "has_category": False,
        "has_dc_subject": False, "has_media_keywords": False, "url_ticker": None,
        "titles": [], "dates": [], "categories": [], "feed_title": "",
    }
    m = URL_TICKER_RE.search(url)
    if m:
        out["url_ticker"] = m.group(1)
    if not body:
        return out
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return out
    # Feed-level title
    chan = root.find("channel")
    if chan is not None:
        out["feed_title"] = chan.findtext("title") or ""
    for item in root.iter("item"):
        out["items"] += 1
        title_text = item.findtext("title") or ""
        desc_text = item.findtext("description") or ""
        combined = title_text + " " + desc_text
        # Collect sample titles (first 5)
        if len(out["titles"]) < 5:
            out["titles"].append(title_text[:120])
        # Collect pub dates (first 5)
        pub = item.findtext("pubDate") or ""
        if pub and len(out["dates"]) < 5:
            out["dates"].append(pub)
        # Collect categories (unique, up to 10)
        for cat_el in item.findall("category"):
            cat_text = (cat_el.text or "").strip()
            if cat_text and cat_text not in out["categories"]:
                out["categories"].append(cat_text)
        for tk in PARENS_TICKER.findall(combined) + CASHTAG_TICKER.findall(combined):
            if tk not in {"US", "USA", "AI", "CEO", "CFO", "IPO", "ETF", "GDP"}:
                out["tickers"].add(tk)
        if item.find("category") is not None:
            out["has_category"] = True
        if item.find("dc:subject", NS) is not None:
            out["has_dc_subject"] = True
        if item.find("media:keywords", NS) is not None:
            out["has_media_keywords"] = True
    # Cap categories list
    out["categories"] = out["categories"][:15]
    return out


def main() -> int:
    import time

    sep = "=" * 80
    for label, url in FEEDS:
        status, ctype, body = fetch(url)
        info = classify(url, body)

        # Improved classification: URL-based ticker = PER_TICKER, else GENERAL
        if info["url_ticker"]:
            klass = f"PER_TICKER (URL pins {info['url_ticker']})"
        elif info["items"]:
            klass = f"GENERAL ({len(info['tickers'])} tickers mentioned across {info['items']} items)"
        else:
            klass = "DEAD/EMPTY (no items parsed)"

        # Freshness check
        if status == 429:
            freshness = "RATE LIMITED"
        elif info["dates"]:
            freshness = info["dates"][0]  # most recent pubDate
        else:
            freshness = "no dates found"

        tags = ", ".join(t for t, ok in [
            ("category", info["has_category"]),
            ("dc:subject", info["has_dc_subject"]),
            ("media:keywords", info["has_media_keywords"]),
        ] if ok) or "none"

        ok_mark = "OK" if status == 200 else ("WARN" if status == 429 else "FAIL")

        print(f"\n{sep}")
        print(f"  [{ok_mark}] {label}")
        print(f"  URL:          {url}")
        print(f"  HTTP:         {status} | {ctype} | {len(body):,}B")
        print(f"  Feed title:   {info['feed_title']}")
        print(f"  Class:        {klass}")
        print(f"  Items:        {info['items']}")
        print(f"  Newest:       {freshness}")
        print(f"  Tickers seen: {sorted(info['tickers'])[:15]}{' ...' if len(info['tickers'])>15 else ''}")
        print(f"  XML tags:     {tags}")
        if info["categories"]:
            print(f"  Categories:   {info['categories'][:10]}")
        if info["titles"]:
            print(f"  Sample titles:")
            for t in info["titles"][:3]:
                print(f"    - {t}")
        if info["dates"] and len(info["dates"]) > 1:
            print(f"  Date range:   {info['dates'][-1]}  -->  {info['dates'][0]}")

        # Small delay to avoid tripping rate limits
        time.sleep(0.5)

    print(f"\n{sep}")
    print(f"\nDone. Probed {len(FEEDS)} feeds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
