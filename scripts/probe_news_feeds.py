#!/usr/bin/env python3
"""Probe candidate RSS news feeds and classify general vs ticker-specific.

Run locally (sandbox blocks outbound HTTP):

    python scripts/probe_news_feeds.py

Reports per feed:
  - HTTP status, content-type, byte size
  - <item> count
  - Distinct $TICKER cashtags + (TKR) parens detected across titles
  - Heuristic class:
      PER_TICKER  if URL templates a ticker OR <=1 distinct ticker in sample
      GENERAL     otherwise
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
    ("SA market currents (general?)", "https://seekingalpha.com/market_currents.xml"),
    ("SA per-ticker AVGO",            "https://seekingalpha.com/api/sa/combined/AVGO.xml"),
    ("Yahoo per-ticker AVGO",         "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AVGO&region=US&lang=en-US"),
    ("CNBC top news",                 "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC markets",                  "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
    ("CNBC earnings",                 "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
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
    for item in root.iter("item"):
        out["items"] += 1
        title = (item.findtext("title") or "") + " " + (item.findtext("description") or "")
        for tk in PARENS_TICKER.findall(title) + CASHTAG_TICKER.findall(title):
            if tk not in {"US", "USA", "AI", "CEO", "CFO", "IPO", "ETF", "GDP"}:
                out["tickers"].add(tk)
        if item.find("category") is not None:
            out["has_category"] = True
        if item.find("dc:subject", NS) is not None:
            out["has_dc_subject"] = True
        if item.find("media:keywords", NS) is not None:
            out["has_media_keywords"] = True
    return out


def main() -> int:
    for label, url in FEEDS:
        status, ctype, body = fetch(url)
        info = classify(url, body)
        if info["url_ticker"]:
            klass = f"PER_TICKER (URL pins {info['url_ticker']})"
        elif info["items"] and len(info["tickers"]) <= 1:
            klass = f"PER_TICKER (≤1 distinct ticker in {info['items']} items)"
        elif info["items"]:
            klass = f"GENERAL ({len(info['tickers'])} distinct tickers across {info['items']} items)"
        else:
            klass = "UNKNOWN (no items parsed)"
        tags = ",".join(t for t, ok in [
            ("category", info["has_category"]),
            ("dc:subject", info["has_dc_subject"]),
            ("media:keywords", info["has_media_keywords"]),
        ] if ok) or "—"
        print(f"\n{label}\n  url:       {url}\n  http:      {status} ({ctype}, {len(body)}B)")
        print(f"  items:     {info['items']}")
        print(f"  tickers:   {sorted(info['tickers'])[:10]}{' …' if len(info['tickers'])>10 else ''}")
        print(f"  tag fields: {tags}")
        print(f"  class:     {klass}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
