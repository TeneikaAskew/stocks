"""Fetch and cache ticker details from Alpha Vantage OVERVIEW endpoint.

Used by the news-feed pipeline to map watchlist tickers to company names,
sectors, and search aliases so headlines like "Intel surges" can be matched
to INTC without manual alias maintenance.

Primary store is Cloud SQL ``ticker_info`` table (per-user capable).
Falls back to ``data/ticker_info.json`` when Cloud SQL is not configured.

Usage:
    from lib.ticker_info import get_ticker_info, get_aliases

    info = get_ticker_info("AVGO")        # dict with Name, Sector, etc.
    aliases = get_aliases("AVGO")          # ["AVGO", "Broadcom", "Broadcom Inc"]
    bulk  = refresh_watchlist_info()       # fetch all watchlist tickers
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_CACHE_PATH = _REPO_ROOT / "data" / "ticker_info.json"
_AV_BASE = "https://www.alphavantage.co/query"

# Fields we keep from the AV OVERVIEW response
_KEEP_FIELDS = [
    "Symbol", "Name", "Exchange", "Sector", "Industry",
    "MarketCapitalization", "Description", "AssetType",
]


# ---------------------------------------------------------------------------
# Cloud SQL persistence
# ---------------------------------------------------------------------------

def _cloud_sql_available() -> bool:
    try:
        from gcp.database import is_cloud_sql_configured
        return is_cloud_sql_configured()
    except ImportError:
        return False


def _upsert_to_cloud_sql(ticker: str, info: dict) -> None:
    """Write a single ticker_info row to Cloud SQL."""
    try:
        from gcp.database import execute_sql
        execute_sql(
            """
            INSERT INTO ticker_info (ticker, name, exchange, sector, industry,
                                     market_cap, description, asset_type, raw_json)
            VALUES (:ticker, :name, :exchange, :sector, :industry,
                    :market_cap, :description, :asset_type, :raw_json)
            ON CONFLICT (ticker) DO UPDATE SET
                name        = EXCLUDED.name,
                exchange    = EXCLUDED.exchange,
                sector      = EXCLUDED.sector,
                industry    = EXCLUDED.industry,
                market_cap  = EXCLUDED.market_cap,
                description = EXCLUDED.description,
                asset_type  = EXCLUDED.asset_type,
                raw_json    = EXCLUDED.raw_json,
                updated_at  = NOW()
            """,
            {
                "ticker": ticker.upper(),
                "name": info.get("Name"),
                "exchange": info.get("Exchange"),
                "sector": info.get("Sector"),
                "industry": info.get("Industry"),
                "market_cap": _safe_bigint(info.get("MarketCapitalization")),
                "description": info.get("Description"),
                "asset_type": info.get("AssetType"),
                "raw_json": json.dumps(info),
            },
        )
    except Exception as exc:
        logger.warning("Cloud SQL upsert for %s failed: %s", ticker, exc)


def _read_from_cloud_sql(ticker: str) -> Optional[dict]:
    """Read a single ticker_info row from Cloud SQL."""
    try:
        from gcp.database import query_to_dataframe
        df = query_to_dataframe(
            "SELECT raw_json, updated_at FROM ticker_info WHERE ticker = :ticker",
            {"ticker": ticker.upper()},
        )
        if df.empty:
            return None
        row = df.iloc[0]
        info = json.loads(row["raw_json"])
        info["_fetched_utc"] = str(row["updated_at"])
        return info
    except Exception as exc:
        logger.warning("Cloud SQL read for %s failed: %s", ticker, exc)
        return None


def _safe_bigint(val) -> Optional[int]:
    if val is None or val == "None" or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Local JSON fallback
# ---------------------------------------------------------------------------

def _load_local_cache() -> dict:
    if _LOCAL_CACHE_PATH.exists():
        try:
            return json.loads(_LOCAL_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("ticker_info local cache corrupt, starting fresh")
    return {}


def _save_local_cache(cache: dict) -> None:
    _LOCAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_CACHE_PATH.write_text(json.dumps(cache, indent=2))


# ---------------------------------------------------------------------------
# Alpha Vantage fetch
# ---------------------------------------------------------------------------

def _get_av_key() -> str:
    from lib.config import AlphaVantageConfig
    return AlphaVantageConfig.get_api_keys()[0]


def fetch_ticker_overview(ticker: str) -> Optional[dict]:
    """Call AV OVERVIEW for a single ticker. Returns trimmed dict or None."""
    from lib.api_client import fetch_with_retry

    try:
        key = _get_av_key()
    except KeyError:
        logger.error("No Alpha Vantage API key configured")
        return None

    params = {
        "function": "OVERVIEW",
        "symbol": ticker.upper(),
        "apikey": key,
    }
    try:
        resp = fetch_with_retry(
            _AV_BASE, params=params, timeout=15,
            circuit_breaker_key="alphavantage",
        )
        data = resp.json()
    except Exception as exc:
        logger.warning("AV OVERVIEW failed for %s: %s", ticker, exc)
        return None

    if not data or "Symbol" not in data:
        note = data.get("Note") or data.get("Information") or ""
        if note:
            logger.warning("AV OVERVIEW %s: %s", ticker, note[:120])
        else:
            logger.warning("AV OVERVIEW returned no data for %s", ticker)
        return None

    return {k: data[k] for k in _KEEP_FIELDS if k in data}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_ticker_info(ticker: str, max_age_days: int = 30) -> Optional[dict]:
    """Return cached ticker info, fetching from AV if stale or missing.

    Checks Cloud SQL first, then local cache, then fetches from AV.
    Writes results to both Cloud SQL and local cache.
    """
    ticker = ticker.upper()
    use_cloud = _cloud_sql_available()

    # 1. Try Cloud SQL
    if use_cloud:
        entry = _read_from_cloud_sql(ticker)
        if entry and _is_fresh(entry, max_age_days):
            return entry

    # 2. Try local cache
    local_cache = _load_local_cache()
    entry = local_cache.get(ticker)
    if entry and _is_fresh(entry, max_age_days):
        return entry

    # 3. Fetch from AV
    info = fetch_ticker_overview(ticker)
    if info:
        info["_fetched_utc"] = datetime.now(timezone.utc).isoformat()
        # Persist to both stores
        if use_cloud:
            _upsert_to_cloud_sql(ticker, info)
        local_cache[ticker] = info
        _save_local_cache(local_cache)
        return info

    # Return stale data rather than nothing
    return entry


def _is_fresh(entry: dict, max_age_days: int) -> bool:
    fetched = entry.get("_fetched_utc", "")
    if not fetched:
        return False
    try:
        age = (datetime.now(timezone.utc) -
               datetime.fromisoformat(str(fetched).replace(" ", "T").rstrip("Z") + "+00:00"
                                      if "+" not in str(fetched) and "Z" not in str(fetched)
                                      else str(fetched))).days
        return age < max_age_days
    except (ValueError, TypeError):
        return False


def search_tickers(keywords: str, limit: int = 10) -> list[dict]:
    """Search for tickers by keyword using AV SYMBOL_SEARCH endpoint.

    Returns a list of match dicts with keys:
        symbol, name, type, region, currency, match_score

    Useful for auto-complete when a user wants to add a ticker to their
    watchlist by company name (e.g. "broadcom" -> AVGO).
    """
    from lib.api_client import fetch_with_retry

    try:
        key = _get_av_key()
    except KeyError:
        logger.error("No Alpha Vantage API key configured")
        return []

    params = {
        "function": "SYMBOL_SEARCH",
        "keywords": keywords,
        "apikey": key,
    }
    try:
        resp = fetch_with_retry(
            _AV_BASE, params=params, timeout=15,
            circuit_breaker_key="alphavantage",
        )
        data = resp.json()
    except Exception as exc:
        logger.warning("AV SYMBOL_SEARCH failed for '%s': %s", keywords, exc)
        return []

    matches = data.get("bestMatches", [])
    results = []
    for m in matches[:limit]:
        results.append({
            "symbol": m.get("1. symbol", ""),
            "name": m.get("2. name", ""),
            "type": m.get("3. type", ""),
            "region": m.get("4. region", ""),
            "currency": m.get("8. currency", ""),
            "match_score": float(m.get("9. matchScore", 0)),
        })
    return results


def get_quote(ticker: str) -> Optional[dict]:
    """Fetch latest price and volume for a ticker using AV GLOBAL_QUOTE.

    Returns a dict with keys:
        symbol, open, high, low, price, volume, latest_trading_day,
        previous_close, change, change_percent

    Returns None on failure.
    """
    from lib.api_client import fetch_with_retry

    try:
        key = _get_av_key()
    except KeyError:
        logger.error("No Alpha Vantage API key configured")
        return None

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker.upper(),
        "apikey": key,
    }
    try:
        resp = fetch_with_retry(
            _AV_BASE, params=params, timeout=15,
            circuit_breaker_key="alphavantage",
        )
        data = resp.json()
    except Exception as exc:
        logger.warning("AV GLOBAL_QUOTE failed for %s: %s", ticker, exc)
        return None

    gq = data.get("Global Quote", {})
    if not gq or "01. symbol" not in gq:
        note = data.get("Note") or data.get("Information") or ""
        if note:
            logger.warning("AV GLOBAL_QUOTE %s: %s", ticker, note[:120])
        return None

    return {
        "symbol": gq.get("01. symbol", ""),
        "open": _safe_float(gq.get("02. open")),
        "high": _safe_float(gq.get("03. high")),
        "low": _safe_float(gq.get("04. low")),
        "price": _safe_float(gq.get("05. price")),
        "volume": _safe_bigint(gq.get("06. volume")),
        "latest_trading_day": gq.get("07. latest trading day", ""),
        "previous_close": _safe_float(gq.get("08. previous close")),
        "change": _safe_float(gq.get("09. change")),
        "change_percent": gq.get("10. change percent", ""),
    }


def _safe_float(val) -> Optional[float]:
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_aliases(ticker: str) -> list[str]:
    """Return search strings for matching headlines to this ticker.

    Always includes the ticker symbol. Adds company name variants
    from the AV OVERVIEW ``Name`` field.

    Example: get_aliases("AVGO") -> ["AVGO", "Broadcom Inc", "Broadcom"]
    """
    ticker = ticker.upper()
    aliases = [ticker]
    info = get_ticker_info(ticker)
    if not info or "Name" not in info:
        return aliases

    full_name = info["Name"].strip()
    if full_name:
        aliases.append(full_name)
        # Add shortened name (strip common suffixes)
        for suffix in [" Inc", " Corp", " Ltd", " Co", " PLC", " NV",
                       " SE", " SA", " AG", " Group", " Holdings",
                       " Incorporated", " Corporation", " Limited",
                       " Company", " Technologies", " Technology"]:
            if full_name.endswith(suffix):
                short = full_name[: -len(suffix)].strip().rstrip(",")
                if short and short != ticker:
                    aliases.append(short)
                break

    return aliases


def refresh_watchlist_info() -> dict[str, dict]:
    """Fetch/refresh AV OVERVIEW for every ticker on the watchlist.

    Returns {ticker: info_dict} for all successfully fetched tickers.
    """
    import time
    from lib.config import AlphaVantageConfig

    try:
        from gcp.fetchers._watchlist import load_watchlist
    except ImportError:
        cfg_path = _REPO_ROOT / "alert_config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            tickers = [t.upper() for t in (data.get("watchlist") or [])]
        else:
            logger.error("Cannot load watchlist")
            return {}
    else:
        tickers = load_watchlist()

    if not tickers:
        logger.info("Watchlist is empty, nothing to refresh")
        return {}

    delay = AlphaVantageConfig().delay_between_calls
    results = {}
    for tk in tickers:
        info = get_ticker_info(tk, max_age_days=0)  # force refresh
        if info:
            results[tk] = info
            logger.info("Fetched %s: %s", tk, info.get("Name", "?"))
        else:
            logger.warning("Failed to fetch info for %s", tk)
        time.sleep(delay)

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "search":
        # Usage: python -m lib.ticker_info search broadcom
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "microsoft"
        print(f"\nSearching for: {query}")
        matches = search_tickers(query)
        for m in matches:
            print(f"  {m['symbol']:10s} {m['name'][:50]:50s} {m['type']:10s} score={m['match_score']:.2f}")
    elif len(sys.argv) > 1 and sys.argv[1] == "quote":
        # Usage: python -m lib.ticker_info quote AVGO
        ticker = sys.argv[2] if len(sys.argv) > 2 else "SPY"
        quote = get_quote(ticker)
        if quote:
            print(f"\n{ticker} quote:")
            for k, v in quote.items():
                print(f"  {k:20s} {v}")
        else:
            print(f"No quote for {ticker}")
    elif len(sys.argv) > 1 and sys.argv[1] == "info":
        # Usage: python -m lib.ticker_info info AVGO
        ticker = sys.argv[2] if len(sys.argv) > 2 else "AVGO"
        info = get_ticker_info(ticker, max_age_days=0)
        if info:
            print(f"\n{ticker} details:")
            for k, v in info.items():
                if k.startswith("_"):
                    continue
                display = str(v)[:100] if k == "Description" else v
                print(f"  {k:25s} {display}")
            print(f"  Aliases: {get_aliases(ticker)}")
        else:
            print(f"No info found for {ticker}")
    else:
        # Default: refresh all watchlist tickers
        results = refresh_watchlist_info()
        print(f"\nRefreshed {len(results)} tickers:")
        for tk, info in results.items():
            aliases = get_aliases(tk)
            print(f"  {tk}: {info.get('Name', '?')} | {info.get('Sector', '?')} | aliases={aliases}")
