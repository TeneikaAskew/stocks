"""Ticker metadata, peers, and news from Alpha Vantage + FinViz.

Provides:
    - AV OVERVIEW: company name, sector, industry (cached to Cloud SQL + local JSON)
    - AV SYMBOL_SEARCH: autocomplete by company name
    - AV GLOBAL_QUOTE: latest price/volume
    - FinViz peers: ``ticker_peer()`` returns 10 peer tickers per symbol
    - FinViz news: ``ticker_news()`` returns up to 100 per-ticker headlines
    - Alias derivation for headline-to-ticker matching

Primary store is Cloud SQL ``ticker_info`` table (per-user capable).
Falls back to ``data/ticker_info.json`` when Cloud SQL is not configured.

Usage:
    from lib.ticker_info import get_ticker_info, get_aliases, get_peers, get_finviz_news

    info  = get_ticker_info("AVGO")       # dict with Name, Sector, etc.
    aliases = get_aliases("AVGO")          # ["AVGO", "Broadcom Inc", "Broadcom"]
    peers = get_peers("AVGO")             # ["QCOM", "NVDA", "TXN", ...]
    news  = get_finviz_news("AVGO")       # [{"date": ..., "title": ..., "link": ..., "source": ...}]
"""

from __future__ import annotations

import json
import threading
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lib.single_flight import SingleFlight

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

# Serialises the load / modify / save sequence on the shared cache file.
# `get_ticker_info` and `get_peers` each read the whole file, change their own
# key, and write the whole file back. Under threadpool dispatch two requests
# for DIFFERENT tickers do that concurrently and the later write discards the
# earlier one's new entry.
#
# Per-process, so it does not coordinate across Cloud Run instances — which is
# why `_save_local_cache` also publishes atomically below. The lock stops the
# lost update; the atomic rename stops the torn read.
_LOCAL_CACHE_LOCK = threading.RLock()


def _load_local_cache() -> dict:
    with _LOCAL_CACHE_LOCK:
        if _LOCAL_CACHE_PATH.exists():
            try:
                return json.loads(_LOCAL_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("ticker_info local cache corrupt, starting fresh")
        return {}


def _save_local_cache(cache: dict) -> None:
    """Publish the cache atomically.

    `write_text` truncates in place, so a concurrent reader could catch the
    file empty or half-written, hit the `except` above, and "start fresh" —
    then save its own single entry over everything. Rendering to a temp file
    in the same directory and `os.replace`-ing it means a reader sees either
    the whole old file or the whole new one, never a partial one.
    """
    with _LOCAL_CACHE_LOCK:
        _LOCAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LOCAL_CACHE_PATH.with_suffix(
            _LOCAL_CACHE_PATH.suffix + f".{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, _LOCAL_CACHE_PATH)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


def _merge_into_local_cache(ticker: str, updates: dict, *, replace: bool) -> None:
    """Atomically fold `updates` into one ticker's entry.

    The callers previously did load -> fetch from the network -> modify -> save,
    and the lock lived INSIDE `_load_local_cache` / `_save_local_cache`, so it
    was released for the whole middle. Two concurrent misses for different
    tickers therefore both read the same file and the later save still
    discarded the earlier entry: the lock was in the wrong place, and the test
    that "proved" otherwise passed only because the test itself wrapped the
    sequence.

    Holding the lock across the AlphaVantage fetch is not the fix either -- it
    would serialise every vendor call in the process. So the fetch stays
    outside, and the cache is RE-READ under the lock here, immediately before
    the write. Whatever another thread stored in the meantime is preserved.

    `replace=True` overwrites the ticker's entry (a fresh overview);
    `replace=False` merges keys into whatever is there (peers, which must not
    drop an overview stored concurrently).
    """
    with _LOCAL_CACHE_LOCK:
        cache = _load_local_cache()          # RLock: re-entrant by design
        if replace:
            cache[ticker] = updates
        else:
            cache.setdefault(ticker, {}).update(updates)
        _save_local_cache(cache)


# Coalesces concurrent vendor lookups per ticker. Threadpool dispatch is what
# made this reachable: while every API handler ran on the event loop, two
# requests for the same cold ticker could not overlap, so the vendor was called
# once no matter how many arrived. Now they can, and both pass the Cloud SQL
# and local-cache checks before either persists — spending two AlphaVantage
# calls, or two FinViz scrapes, on one answer.
#
# `_merge_into_local_cache` does not help here: it makes the WRITE atomic,
# which is a different problem. The circuit breaker does not either; it counts
# failures, and these are successes.
#
# **Nobody waits.** A first version had a decliner wait up to 20 s for the
# claimant, reasoning that it had nothing honest to return. That reasoning
# only considers the waiter and ignores its cost: these are called from
# threadpooled request handlers, so each waiter holds a FastAPI worker, and a
# burst on one ticker can fill the pool and starve `/api/health` and
# `/api/me`. That is the same trade this whole migration exists to remove,
# and the same argument I had already lost once on the freshness audit. The
# bound did not even hold -- 20 s expires before `fetch_with_retry`'s three
# 15 s attempts plus backoff, so waiters would time out and duplicate the
# call anyway, having parked a worker for 20 s to achieve nothing.
#
# So a decliner serves what the cache has and never blocks. What it does NOT
# do is fabricate an answer: with nothing cached at all it falls through and
# fetches, because a transient 404 on a valid ticker would be a made-up
# "no info for IWM" (Rule 3.7) and a duplicate vendor call is the cheaper
# wrong thing.
#
# Which means the coalescing bites exactly where it is worth having: a
# STALE-but-present entry, the common case at a 30-day freshness window,
# where one caller refreshes and the rest are served immediately. A
# stone-cold ticker under concurrency still duplicates, deliberately.
_INFO_FLIGHT = SingleFlight()
_PEERS_FLIGHT = SingleFlight()


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

    # 3. Fetch from AV, once per ticker where the cache can serve the rest.
    with _INFO_FLIGHT.claim(ticker) as mine:
        # Re-read on both branches. A decliner re-reads because a claimant may
        # already have stored the answer; a CLAIMANT re-reads because the cache
        # checks above happened before the claim, so it may have taken the
        # claim moments after a previous claimant finished.
        cached = _load_local_cache().get(ticker)
        if cached and _is_fresh(cached, max_age_days):
            return cached
        if not mine and cached:
            return cached          # stale, but real, and immediate
        # Either we own the fetch, or we own nothing and have nothing to
        # serve. Both fetch; see the note above _INFO_FLIGHT.

        info = fetch_ticker_overview(ticker)
        if info:
            info["_fetched_utc"] = datetime.now(timezone.utc).isoformat()
            # Persist to both stores
            if use_cloud:
                _upsert_to_cloud_sql(ticker, info)
            # `replace=True` drops everything else under the ticker, and
            # `_peers` is stored independently by `get_peers()` under its own
            # flight -- so an overview refresh racing a peers refresh could
            # discard peers that had just been scraped, and `get_peers` does
            # not read them back from the Cloud SQL relationships column, so
            # the next request scrapes FinViz again. Carry them across.
            existing_peers = (_load_local_cache().get(ticker) or {}).get("_peers")
            if existing_peers is not None and "_peers" not in info:
                info["_peers"] = existing_peers
            _merge_into_local_cache(ticker, info, replace=True)
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


# ---------------------------------------------------------------------------
# FinViz: peers and news
# ---------------------------------------------------------------------------

def get_peers(ticker: str, max_age_days: int = 30) -> list[str]:
    """Return peer tickers from FinViz, cached in local JSON and Cloud SQL.

    Uses ``finvizfinance.quote.finvizfinance.ticker_peer()`` which scrapes
    the FinViz quote page. Returns ~10 peer tickers.

    Falls back to same-industry screener if ticker_peer() returns empty.
    """
    ticker = ticker.upper()

    # Check cache first
    local_cache = _load_local_cache()
    entry = local_cache.get(ticker, {})
    cached_peers = entry.get("_peers")
    if cached_peers is not None and _is_fresh(entry, max_age_days):
        return cached_peers

    with _PEERS_FLIGHT.claim(ticker) as mine:
        # Re-read on both branches, for the same reasons as get_ticker_info.
        cached = _load_local_cache().get(ticker, {})
        cached_peers = cached.get("_peers")
        if cached_peers is not None and _is_fresh(cached, max_age_days):
            return cached_peers
        if not mine and cached_peers is not None:
            return cached_peers    # stale, but real, and immediate

        peers = _fetch_finviz_peers(ticker)

        # Persist to cache
        if peers is not None:
            _merge_into_local_cache(ticker, {
                "_peers": peers,
                "_fetched_utc": datetime.now(timezone.utc).isoformat(),
            }, replace=False)

            # Also persist to Cloud SQL relationships column
            if _cloud_sql_available():
                _upsert_peers_to_cloud_sql(ticker, peers)

    return peers or []


_FINVIZ_TIMEOUT = 15  # seconds — finvizfinance has no built-in timeout


def _run_with_timeout(fn, timeout: int = _FINVIZ_TIMEOUT):
    """Run a callable with a timeout. Returns result or raises TimeoutError."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        return future.result(timeout=timeout)


def _fetch_finviz_peers(ticker: str) -> Optional[list[str]]:
    """Fetch peers from FinViz. Returns list of ticker strings or None."""
    try:
        from finvizfinance.quote import finvizfinance

        def _do():
            stock = finvizfinance(ticker)
            return stock.ticker_peer()

        peers = _run_with_timeout(_do)
        if isinstance(peers, list) and peers:
            logger.info("FinViz peers for %s: %s", ticker, peers)
            return peers
    except Exception as exc:
        logger.warning("FinViz ticker_peer() failed for %s: %s", ticker, exc)

    # Fallback: same-industry screener
    return _fetch_industry_peers(ticker)


def _fetch_industry_peers(ticker: str) -> Optional[list[str]]:
    """Fallback: find peers by querying FinViz screener for same industry."""
    try:
        from finvizfinance.quote import finvizfinance
        from finvizfinance.screener.overview import Overview

        stock = finvizfinance(ticker)
        fund = stock.ticker_fundament()
        industry = fund.get("Industry")
        if not industry:
            return None

        foverview = Overview()
        foverview.set_filter(filters_dict={"Industry": industry})
        df = foverview.screener_view()
        if df is None or df.empty:
            return None

        # Top 10 by market cap, excluding self
        df_sorted = df[df["Ticker"] != ticker].sort_values(
            "Market Cap", ascending=False
        )
        peers = df_sorted["Ticker"].head(10).tolist()
        logger.info("FinViz industry peers for %s (%s): %s", ticker, industry, peers)
        return peers
    except Exception as exc:
        logger.warning("FinViz industry screener failed for %s: %s", ticker, exc)
        return None


def _upsert_peers_to_cloud_sql(ticker: str, peers: list[str]) -> None:
    """Write peers to the relationships JSONB column in ticker_info."""
    try:
        from gcp.database import execute_sql
        execute_sql(
            """
            UPDATE ticker_info
            SET relationships = jsonb_set(
                COALESCE(relationships, '{}'::jsonb),
                '{peers}',
                :peers_json::jsonb
            ),
            updated_at = NOW()
            WHERE ticker = :ticker
            """,
            {"ticker": ticker.upper(), "peers_json": json.dumps(peers)},
        )
    except Exception as exc:
        logger.warning("Cloud SQL peers upsert for %s failed: %s", ticker, exc)


def get_finviz_news(ticker: str) -> list[dict]:
    """Return recent news articles for a ticker from FinViz.

    Uses ``finvizfinance.quote.finvizfinance.ticker_news()`` which scrapes
    the FinViz quote page. Returns up to 100 articles with keys:
        date, title, link, source

    Not cached — intended to be called by the RSS fetcher on each poll cycle.
    """
    ticker = ticker.upper()
    try:
        from finvizfinance.quote import finvizfinance

        def _do():
            stock = finvizfinance(ticker)
            return stock.ticker_news()

        df = _run_with_timeout(_do)
        if df is None or df.empty:
            return []
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "date": str(row.get("Date", "")),
                "title": str(row.get("Title", "")).strip(),
                "link": str(row.get("Link", "")).strip(),
                "source": str(row.get("Source", "")).strip(),
            })
        logger.info("FinViz news for %s: %d articles", ticker, len(rows))
        return rows
    except Exception as exc:
        logger.warning("FinViz ticker_news() failed for %s: %s", ticker, exc)
        return []


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
        logger.error("gcp.fetchers._watchlist not importable; cannot load watchlist")
        return {}
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
    elif len(sys.argv) > 1 and sys.argv[1] == "peers":
        # Usage: python -m lib.ticker_info peers AVGO
        ticker = sys.argv[2] if len(sys.argv) > 2 else "AVGO"
        peers = get_peers(ticker, max_age_days=0)
        print(f"\n{ticker} peers ({len(peers)}): {peers}")
    elif len(sys.argv) > 1 and sys.argv[1] == "news":
        # Usage: python -m lib.ticker_info news AVGO
        ticker = sys.argv[2] if len(sys.argv) > 2 else "AVGO"
        articles = get_finviz_news(ticker)
        print(f"\n{ticker} news ({len(articles)} articles):")
        for a in articles[:10]:
            print(f"  {a['date']} | {a['title'][:70]} | {a['source']}")
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
