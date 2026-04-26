"""Shared helper: load the configured watchlist for fetcher ticker unions.

The new fetchers (`fetch_sec_filings`, `fetch_earnings_history`,
`fetch_insider_transactions`, `fetch_news_sentiment`) default their
ticker universe to the next-7-day earnings_calendar window. That misses
names the user actively cares about whose next earnings are far out
(e.g. AVGO with a June report won't appear in the April 7d window).

This helper loads the curated watchlist from `alert_config.json` so
each fetcher can union it into its default ticker pool. Anything in
`alert_config.json` → `"watchlist"` is always scraped, regardless of
when (or whether) the ticker reports earnings.

Resolution order:
  1. `alert_config.json` `"watchlist"` array (project root)
  2. `INSIGHT_TICKERS` env var (comma-separated)
  3. Empty list — caller decides whether to fall back further.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# alert_config.json lives at the repo root; this file is at gcp/fetchers/.
_CFG_PATH = Path(__file__).resolve().parents[2] / "alert_config.json"


def load_watchlist() -> list[str]:
    """Return the configured watchlist (uppercased, deduped, order preserved)."""
    try:
        if _CFG_PATH.exists():
            data = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
            wl = data.get("watchlist") or []
            if isinstance(wl, list) and wl:
                return _dedupe_upper(wl)
    except Exception as exc:
        logger.warning("watchlist load failed (%s); falling back to env", exc)

    env = os.environ.get("INSIGHT_TICKERS", "")
    if env:
        return _dedupe_upper(env.split(","))
    return []


def _dedupe_upper(tickers) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in tickers:
        tk = str(raw).strip().upper()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out
