"""
Grid + Nodes router — 2-D strike × expiration heatmap surface.

Endpoints:

  GET /api/options/{ticker}/grid             — live (realtime → EOD fallback
                                                → on-demand AV dispatch)
  GET /api/options/{ticker}/{date}/grid      — historical (EOD archive)
  GET /api/options/{ticker}/nodes            — live, semantic taxonomy
  GET /api/options/{ticker}/{date}/nodes     — historical, semantic taxonomy
  GET /api/options/{ticker}/grid/timeseries  — realtime-only rate-of-change

Phases:
  B1 (shipped) — read-side endpoints reading from etf_options_snapshots.
  B2 (this PR) — on-demand AV dispatch for off-list tickers, inline BSM
                 Greeks solver for SPX/NDX/RUT/XSP, per-IP rate limit,
                 /grid/timeseries.

Data source contract (Track 1 tiered loader, extended for B2):

  Live mode (no `{date}` in path):
    1. Most recent REALTIME row strictly before `now` →
       data_source = 'realtime'
    2. else most recent EOD row, ≤2 trading days behind →
       data_source = 'eod_fallback'
    3. else 3-5 trading days behind →
       data_source = 'stale_fallback'
    4. else if ticker is reachable via AV REALTIME_OPTIONS and the
       per-IP rate limit isn't exceeded →
       fire on-demand AV call, optionally enrich with BSM Greeks for
       index tickers, persist to etf_options_snapshots, return as
       data_source = 'realtime'.
    5. else (or AV error) →
       data_source = 'unavailable' (HTTP 200, empty payload)

  Historical mode (`{date}` in path):
    Most recent EOD row with snapshot_date ≤ requested date.
    Never reads realtime; never invokes on-demand AV — past-date
    intraday data is meaningless unless explicitly requested via
    /grid/timeseries.

Tickers covered (B2):
  - SPY / IWM / QQQ: live realtime via fetch_av_realtime_options.py
  - SPX, NDX, watchlist single names: live EOD-fallback via the nightly
    fetch_av_historical_options.py write; on-demand also available
    for fresh intraday lookups, with inline BSM solver for index Greeks.
  - Anything else: on-demand AV dispatch on first request, then cached
    in Cloud SQL for ~60s for repeat lookups.

Per-IP rate limit (B2):
  10 unique on-demand tickers per IP per rolling 60-second window.
  Scheduled-list tickers (SPY/IWM/QQQ) don't count against the cap —
  they're served from Cloud SQL.
"""
from __future__ import annotations

import logging
import os
from datetime import date as date_type, datetime, timezone
from pathlib import Path
import sys
from typing import Optional

import numpy as np
import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query, Request, Response

# Project root → so `from lib import gamma` resolves (matches other routers)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib import gamma  # noqa: E402
from lib.agents.summarizers import (  # noqa: E402
    classify_gamma_freshness,
    MAX_OPTIONS_HARD_STALE_TRADING_DAYS,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Caches ────────────────────────────────────────────────────────────────
#
# Live grid: 60 s TTL — matches the realtime fetcher's 5-min cadence and
#            the existing OptionsFlowPage auto-refresh interval (no point
#            caching longer than the underlying data refreshes).
# Historical grid: 12 h TTL — EOD rows are immutable once written.

_LIVE_GRID_CACHE: TTLCache = TTLCache(maxsize=64, ttl=60)
_HIST_GRID_CACHE: TTLCache = TTLCache(maxsize=512, ttl=43200)
_NODES_CACHE: TTLCache = TTLCache(maxsize=128, ttl=60)
_HIST_NODES_CACHE: TTLCache = TTLCache(maxsize=512, ttl=43200)


# ─── Helpers ───────────────────────────────────────────────────────────────


def _require_cloud_sql() -> None:
    """Lazy-import gate — same pattern other routers use."""
    from gcp.database import is_cloud_sql_configured  # noqa: WPS433
    if not is_cloud_sql_configured():
        raise HTTPException(
            status_code=503,
            detail="Cloud SQL not configured — set DB_USER / DB_PASS / "
                   "CLOUD_SQL_CONNECTION_NAME.",
        )


def _validate_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if not t or not t.replace(".", "").isalnum() or len(t) > 10:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker!r}")
    return t


def _validate_date(date_str: str) -> date_type:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date {date_str!r} — expected YYYY-MM-DD",
        )


def _df_to_contracts(df: pd.DataFrame) -> list[dict]:
    """Map an `etf_options_snapshots` rowset to `lib.gamma` contract dicts.

    The gamma math expects:
      type ('call'|'put'), strike, expiration (ISO string),
      open_interest, gamma, vega, delta (optional),
      bid, ask, mark, last (for parity-based spot estimate),
      volume (for OI-volume context).
    """
    contracts: list[dict] = []
    for _, row in df.iterrows():
        ot = row.get("option_type")
        # The schema stores 'calls'/'puts'; the math expects 'call'/'put'
        # (singular) per lib.gamma.aggregate_by_strike's switch.
        if ot == "calls":
            t = "call"
        elif ot == "puts":
            t = "put"
        else:
            continue
        exp = row.get("expiration")
        if hasattr(exp, "isoformat"):
            exp = exp.isoformat()[:10]
        contracts.append({
            "type": t,
            "strike": float(row.get("strike") or 0.0),
            "expiration": str(exp)[:10] if exp is not None else None,
            "open_interest": _safe_float(row.get("open_interest")),
            "volume": _safe_float(row.get("volume")),
            "implied_volatility": _safe_float(row.get("implied_volatility")),
            "delta": _safe_float(row.get("delta")),
            "gamma": _safe_float(row.get("gamma")),
            "theta": _safe_float(row.get("theta")),
            "vega": _safe_float(row.get("vega")),
            "rho": _safe_float(row.get("rho")),
            "bid": _safe_float(row.get("bid")),
            "ask": _safe_float(row.get("ask")),
            "mark": _safe_float(row.get("mark")),
            "last": _safe_float(row.get("last_price")),
        })
    return contracts


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def _unavailable_envelope(ticker: str, reason: str) -> dict:
    """Typed UNAVAILABLE envelope per CLAUDE.md Rule 3.7 §EXTERNAL —
    returns HTTP 200 with a well-formed payload the UI can render
    cleanly (no synthetic numbers; no empty cells masquerading as
    data; no crash)."""
    return {
        "ticker": ticker.upper(),
        "snapshot_date": None,
        "snapshot_ts": None,
        "data_source": "unavailable",
        "reason": reason,
        "spot": None,
        "gamma_balance": None,
        "gamma_flip": None,
        "regime": "unknown",
        "total_gex": 0.0,
        "total_vex": 0.0,
        "cells": [],
        "expirations": [],
        "strikes": [],
        "window_pct": 0.0,
        "warnings": [reason],
    }


# ─── Data loader: tiered realtime → EOD fallback ───────────────────────────


def _load_chain_for_live(
    ticker: str, today: Optional[date_type] = None,
) -> tuple[list[dict], Optional[str], Optional[date_type], str, int]:
    """Load chain rows for the live grid endpoint.

    Returns: (contracts, snapshot_ts_iso, snapshot_date, data_source, days_behind).
    `data_source` ∈ {'realtime','eod_fallback','stale_fallback','unavailable'}.
    `days_behind` is 0 for realtime, N trading days for fallbacks.
    """
    from gcp.database import query_to_dataframe

    today = today or date_type.today()
    floor = today - pd.Timedelta(days=20)  # 15 trading days × 1.5 margin

    # Phase 1: realtime probe — most recent intraday snapshot strictly
    # before now. Uses idx_etf_options_realtime partial index for speed.
    sql_rt = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               snapshot_ts, snapshot_date
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND market_session = 'REALTIME'
          AND snapshot_date >= :floor
          AND snapshot_ts = (
            SELECT MAX(snapshot_ts) FROM etf_options_snapshots
            WHERE ticker = :ticker
              AND data_source = 'alphavantage'
              AND market_session = 'REALTIME'
              AND snapshot_date >= :floor
          )
        ORDER BY expiration, strike, option_type
    """
    df_rt = query_to_dataframe(sql_rt, {"ticker": ticker, "floor": str(floor)})
    if not df_rt.empty:
        ts_raw = df_rt["snapshot_ts"].iloc[0]
        sd_raw = df_rt["snapshot_date"].iloc[0]
        ts_iso = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw)
        sd = sd_raw if isinstance(sd_raw, date_type) else (
            sd_raw.date() if hasattr(sd_raw, "date") else pd.to_datetime(sd_raw).date()
        )
        return (_df_to_contracts(df_rt), ts_iso, sd, "realtime", 0)

    # Phase 2: EOD fallback — most recent nightly snapshot.
    sql_eod = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               snapshot_ts, snapshot_date
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND (market_session = 'EOD' OR market_session IS NULL)
          AND snapshot_date >= :floor
          AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM etf_options_snapshots
            WHERE ticker = :ticker
              AND data_source = 'alphavantage'
              AND (market_session = 'EOD' OR market_session IS NULL)
              AND snapshot_date >= :floor
          )
        ORDER BY expiration, strike, option_type
    """
    df_eod = query_to_dataframe(sql_eod, {"ticker": ticker, "floor": str(floor)})
    if df_eod.empty:
        return ([], None, None, "unavailable", -1)

    sd_raw = df_eod["snapshot_date"].iloc[0]
    sd = sd_raw if isinstance(sd_raw, date_type) else (
        sd_raw.date() if hasattr(sd_raw, "date") else pd.to_datetime(sd_raw).date()
    )
    days_behind = int(np.busday_count(sd, today))
    tier = classify_gamma_freshness(days_behind)
    if tier == "unavailable":
        return ([], None, sd, "unavailable", days_behind)

    ts_raw = df_eod["snapshot_ts"].iloc[0]
    ts_iso = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw)
    return (_df_to_contracts(df_eod), ts_iso, sd, tier, days_behind)


def _load_session_open_chain(
    ticker: str, session_date: date_type,
) -> tuple[list[dict], Optional[str]]:
    """Load the EARLIEST realtime snapshot of `session_date` — the session-open
    baseline for per-cell intraday %-change.

    Returns (contracts, snapshot_ts_iso). Empty list + None when the session has
    no realtime rows. Exactly ONE query (mirrors the MAX(snapshot_ts) pattern in
    _load_chain_for_live with MIN), index-backed by idx_etf_options_realtime.
    """
    from gcp.database import query_to_dataframe

    sql = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               snapshot_ts, snapshot_date
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND market_session = 'REALTIME'
          AND snapshot_date = :session_date
          AND snapshot_ts = (
            SELECT MIN(snapshot_ts) FROM etf_options_snapshots
            WHERE ticker = :ticker
              AND data_source = 'alphavantage'
              AND market_session = 'REALTIME'
              AND snapshot_date = :session_date
          )
        ORDER BY expiration, strike, option_type
    """
    df = query_to_dataframe(
        sql, {"ticker": ticker, "session_date": str(session_date)})
    if df.empty:
        return ([], None)
    ts_raw = df["snapshot_ts"].iloc[0]
    ts_iso = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw)
    return (_df_to_contracts(df), ts_iso)


def _load_chain_for_historical(
    ticker: str, requested_date: date_type,
) -> tuple[list[dict], Optional[str], Optional[date_type], str, int]:
    """Load chain rows for a historical date — EOD only.

    Returns the same tuple shape as _load_chain_for_live. data_source is
    eod_fallback / stale_fallback / unavailable; never 'realtime'.
    """
    from gcp.database import query_to_dataframe

    sql = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               snapshot_ts, snapshot_date
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND (market_session = 'EOD' OR market_session IS NULL)
          AND snapshot_date <= :req_date
          AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM etf_options_snapshots
            WHERE ticker = :ticker
              AND data_source = 'alphavantage'
              AND (market_session = 'EOD' OR market_session IS NULL)
              AND snapshot_date <= :req_date
          )
        ORDER BY expiration, strike, option_type
    """
    df = query_to_dataframe(sql, {"ticker": ticker, "req_date": str(requested_date)})
    if df.empty:
        return ([], None, None, "unavailable", -1)

    sd_raw = df["snapshot_date"].iloc[0]
    sd = sd_raw if isinstance(sd_raw, date_type) else (
        sd_raw.date() if hasattr(sd_raw, "date") else pd.to_datetime(sd_raw).date()
    )
    days_behind = int(np.busday_count(sd, requested_date))
    tier = classify_gamma_freshness(days_behind)
    if tier == "unavailable":
        return ([], None, sd, "unavailable", days_behind)

    ts_raw = df["snapshot_ts"].iloc[0]
    ts_iso = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw)
    return (_df_to_contracts(df), ts_iso, sd, tier, days_behind)


# ─── On-demand AV dispatch (Phase B2) ──────────────────────────────────────
#
# When neither realtime nor EOD rows exist for a ticker, fire AV
# REALTIME_OPTIONS live. Persists the result to etf_options_snapshots so
# subsequent requests (within 60s for the same query, longer for repeat
# users of the same ticker) read from Cloud SQL — the AV call only fires
# the first time after a cache miss.
#
# Rate-limited per-IP to prevent budget abuse (AV is $200/mo flat for
# 600 req/min; a curious user spamming 100 tickers shouldn't eat
# everyone else's budget).

# Comma-separated env override for tests / staging; defaults to the
# scheduled realtime list. These tickers are NEVER subjected to the
# on-demand path because Cloud SQL always has fresher data for them.
_SCHEDULED_REALTIME_TICKERS = frozenset(
    os.environ.get("GRID_SCHEDULED_TICKERS", "SPY,IWM,QQQ").upper().split(",")
)

# AV API key — same source as fetchers + options.py
_AV_API_KEY = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")

# Per-IP rate limiter — 10 unique tickers per IP per rolling 60s window.
# Keys are IP addresses; values are sets of normalized tickers, with a
# 60s TTL on each entry (the whole set evicts after 60s of idleness).
_ONDEMAND_RATE_LIMIT_TTL = 60
_ONDEMAND_MAX_TICKERS_PER_WINDOW = 10
_ONDEMAND_RATE_CACHE: TTLCache = TTLCache(maxsize=4096, ttl=_ONDEMAND_RATE_LIMIT_TTL)


def _check_ondemand_rate_limit(client_ip: str, ticker: str) -> None:
    """Per-IP per-60s ceiling. Raises 429 when the IP has already
    requested >=10 distinct tickers in the last 60s.

    Repeat requests for the SAME ticker from the same IP don't add
    to the count — only DISTINCT tickers do, which is the actual
    AV-call rate driver. The cache entry TTL acts as the rolling
    window: once an IP goes idle for 60s, its set evicts and the
    counter resets.
    """
    seen = _ONDEMAND_RATE_CACHE.get(client_ip)
    if seen is None:
        seen = set()
        _ONDEMAND_RATE_CACHE[client_ip] = seen
    if ticker in seen:
        return  # already counted; further reads are free
    if len(seen) >= _ONDEMAND_MAX_TICKERS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail=(
                f"On-demand ticker rate limit: {_ONDEMAND_MAX_TICKERS_PER_WINDOW} "
                f"unique tickers per 60s per IP. Try again in 60s, or stick to "
                f"the scheduled-realtime list ({sorted(_SCHEDULED_REALTIME_TICKERS)})."
            ),
            headers={"Retry-After": "60"},
        )
    seen.add(ticker)


def _fetch_on_demand(
    ticker: str, client_ip: str,
) -> tuple[list[dict], Optional[str], Optional[date_type]]:
    """Fire an AV REALTIME_OPTIONS call for `ticker`, optionally enrich
    SPX/NDX-class index tickers with BSM Greeks, persist to Cloud SQL,
    and return the chain rows + snapshot_ts + snapshot_date.

    Raises:
      HTTPException 429 — rate limit exceeded.
      HTTPException 503 — AV unavailable / sample data / tier downgrade
                          / network failure. Caller should propagate this
                          (it's a clear "external resource isn't ready"
                          signal, not silent fallback).

    Returns ([], None, None) only if the call SUCCEEDS but returns 0
    rows (shouldn't happen in practice — would raise the typed
    RealtimeOptionsUnavailable from the fetcher).
    """
    if not _AV_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AV_API_KEY not configured — on-demand fetch unavailable.",
        )

    _check_ondemand_rate_limit(client_ip, ticker)

    # Lazy imports — these pull in pandas + sqlalchemy and we don't
    # want to slow the cold start when the on-demand path isn't used.
    from gcp.database import is_cloud_sql_configured, upsert_dataframe
    from gcp.fetchers.fetch_av_realtime_options import (
        fetch_av_realtime_options,
        RealtimeOptionsUnavailable,
    )

    snapshot_ts = datetime.now(timezone.utc)
    try:
        df = fetch_av_realtime_options(ticker, _AV_API_KEY, snapshot_ts)
    except RealtimeOptionsUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AV REALTIME_OPTIONS unavailable for {ticker}: {exc}",
        )
    except Exception as exc:
        logger.warning(
            "On-demand AV fetch for %s failed with %s: %s",
            ticker, type(exc).__name__, exc,
        )
        raise HTTPException(
            status_code=503,
            detail=f"AV fetch error for {ticker}: {type(exc).__name__}",
        )

    if df.empty:
        return ([], None, None)

    # Inline BSM Greeks solver for SPX/NDX/RUT/XSP — AV returns "-" for
    # index-option Greeks; without this enrichment the gamma math returns
    # zero across the chain (visible as a flat heatmap).
    try:
        from lib.options_greeks import (
            COMPUTE_GREEKS_TICKERS,
            enrich_av_chain_with_greeks,
        )
        if ticker.upper() in COMPUTE_GREEKS_TICKERS:
            snap_date = snapshot_ts.date()
            df = enrich_av_chain_with_greeks(df, ticker, snap_date)
            # Coalesce sidecar *_computed columns into the primary Greek
            # columns so lib.gamma.aggregate_by_strike (which reads
            # `gamma`/`vega` directly) sees the BSM values rather than
            # the empty AV passthroughs.
            sidecar_map = {
                "delta": "delta_computed",
                "gamma": "gamma_computed",
                "theta": "theta_computed",
                "vega":  "vega_computed",
                "rho":   "rho_computed",
                "implied_volatility": "implied_volatility_computed",
            }
            for primary, sidecar in sidecar_map.items():
                if sidecar in df.columns:
                    # Prefer the existing primary value when present;
                    # only fill from BSM when AV returned NaN. This
                    # protects against accidentally overwriting an
                    # AV-supplied Greek with a less-accurate BSM one.
                    df[primary] = df[primary].where(df[primary].notna(), df[sidecar])
    except Exception as exc:
        # BSM enrichment failure is non-fatal — return the AV chain
        # with NaN Greeks. The heatmap will be flat for SPX but other
        # tickers (NVDA, TSLA) won't reach this branch at all (they're
        # not in COMPUTE_GREEKS_TICKERS).
        logger.warning(
            "BSM enrichment failed for %s: %s: %s",
            ticker, type(exc).__name__, exc,
        )

    # Persist so subsequent requests are cache hits, not new AV calls.
    if is_cloud_sql_configured():
        try:
            conflict_cols = ['ticker', 'snapshot_ts', 'option_type',
                             'expiration', 'strike']
            # Match the existing dedup behavior of the fetcher itself —
            # AV occasionally returns duplicate contract rows within one
            # response.
            df_unique = df.drop_duplicates(subset=conflict_cols, keep='last')
            upsert_dataframe(df_unique, 'etf_options_snapshots', conflict_cols)
            logger.info(
                "On-demand fetch persisted: ticker=%s rows=%d snapshot_ts=%s",
                ticker, len(df_unique), snapshot_ts.isoformat(),
            )
        except Exception as exc:
            # Persist failure is non-fatal — the user still gets their
            # data this request; next request will hit AV again. Log
            # loudly so the operator sees it.
            logger.error(
                "On-demand persist failed for %s: %s: %s",
                ticker, type(exc).__name__, exc,
            )

    return (
        _df_to_contracts(df),
        snapshot_ts.isoformat(),
        snapshot_ts.date(),
    )


# ─── /grid endpoints ───────────────────────────────────────────────────────


@router.get("/api/options/{ticker}/grid")
async def get_grid_live(
    ticker: str,
    request: Request,
    response: Response,
    strike_window_pct: float = Query(8.0, ge=0.5, le=50.0,
                                      description="Display window around spot in PERCENT"),
    expirations: Optional[str] = Query(None,
                                        description="Comma-separated ISO dates to whitelist"),
    allow_on_demand: bool = Query(True,
                                   description="Allow on-demand AV dispatch when Cloud SQL has no data"),
    include_change: bool = Query(True,
                                  description="Overlay per-cell intraday %-change vs session open (realtime only)"),
):
    """Live 2-D strike × expiration grid.

    Internal routing (B2):
      - SPY / IWM / QQQ → realtime row from `market_session='REALTIME'`
      - SPX / NDX / RUT / XSP → EOD-fallback (BSM Greeks already there
        for these; on-demand AV available with inline BSM solver)
      - Watchlist single names (NVDA, AVGO, ...) → EOD-fallback or
        on-demand if EOD is also missing
      - Anything else → on-demand AV dispatch (rate-limited to 10 unique
        tickers per IP per 60s); ticker gets persisted on first hit so
        repeat readers are cache hits

    Returns the `GammaGridSummary` JSON shape — see lib.gamma.

    Cached 60 s. Cache headers: public, max-age=60.
    """
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    cache_key = (ticker_upper, round(strike_window_pct, 2), expirations or "",
                 include_change)
    cached = _LIVE_GRID_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
        return cached

    contracts, ts_iso, snapshot_date, data_source, _days = _load_chain_for_live(
        ticker_upper,
    )

    # Phase B2: on-demand AV dispatch for off-list tickers when no
    # Cloud SQL data exists. Scheduled-list tickers always have data
    # (Track 0 fetcher keeps them current); off-list tickers are
    # eligible for one-off live fetches.
    if (data_source == "unavailable"
            and allow_on_demand
            and ticker_upper not in _SCHEDULED_REALTIME_TICKERS):
        try:
            client_ip = request.client.host if request.client else "unknown"
            contracts, ts_iso, snapshot_date = _fetch_on_demand(
                ticker_upper, client_ip,
            )
            data_source = "realtime" if contracts else "unavailable"
        except HTTPException:
            raise   # propagate 429 / 503 — typed signals the UI can render
        except Exception as exc:
            # Defensive — _fetch_on_demand already catches and re-raises
            # as HTTPException, but if anything slips through we surface
            # an unavailable envelope rather than crash the request.
            logger.error("On-demand dispatch panic for %s: %s: %s",
                          ticker_upper, type(exc).__name__, exc)

    if data_source == "unavailable" or not contracts:
        envelope = _unavailable_envelope(
            ticker_upper,
            "no realtime or EOD chain found within the lookup window"
            + (" (on-demand fetch skipped)" if not allow_on_demand else ""),
        )
        # Don't cache unavailable responses — operator wants to see
        # the moment data appears, not a stale "no data" reply.
        return envelope

    exp_filter = [e.strip() for e in expirations.split(",")] if expirations else None

    # Per-cell intraday %-change overlay — realtime path only. EOD/stale have a
    # single snapshot/day, so an intraday "change" is meaningless (cells keep
    # pct_change=None and the UI hides the badges). One extra bounded query.
    base_contracts: list[dict] = []
    base_ts: Optional[str] = None
    extra_warning: Optional[str] = None
    if include_change and data_source == "realtime" and snapshot_date is not None:
        base_contracts, base_ts = _load_session_open_chain(
            ticker_upper, snapshot_date)
        if base_ts is not None and base_ts == ts_iso:
            # Session just opened — open IS the latest snapshot. Treat as "no
            # delta available yet" rather than a wall of 0.0% badges.
            base_contracts = []
            extra_warning = "session just opened — intraday change not yet available"

    if base_contracts:
        summary = gamma.build_grid_summary_with_change(
            ticker_upper,
            snapshot_date.isoformat() if snapshot_date else "",
            contracts,
            base_contracts,
            snapshot_ts=ts_iso,
            data_source=data_source,
            window_pct=strike_window_pct,
            expirations_filter=exp_filter,
        )
    else:
        summary = gamma.build_grid_summary(
            ticker_upper,
            snapshot_date.isoformat() if snapshot_date else "",
            contracts,
            snapshot_ts=ts_iso,
            data_source=data_source,
            window_pct=strike_window_pct,
            expirations_filter=exp_filter,
        )
    if extra_warning:
        summary.warnings.append(extra_warning)
    payload = summary.to_dict()
    _LIVE_GRID_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=60"
    return payload


@router.get("/api/options/{ticker}/{date_str}/grid")
async def get_grid_historical(
    ticker: str,
    date_str: str,
    response: Response,
    strike_window_pct: float = Query(8.0, ge=0.5, le=50.0,
                                      description="Display window around spot in PERCENT"),
    expirations: Optional[str] = Query(None,
                                        description="Comma-separated ISO dates to whitelist"),
):
    """Historical 2-D grid for a past date — EOD only.

    Reads from `etf_options_snapshots WHERE market_session='EOD'` (or
    NULL — legacy rows). Falls back to the most recent EOD at or before
    the requested date; flags `stale_fallback` if 3-5 trading days
    behind, `unavailable` past that.

    Cached 12 h (EOD rows are immutable).
    """
    ticker_upper = _validate_ticker(ticker)
    requested_date = _validate_date(date_str)
    _require_cloud_sql()

    cache_key = (ticker_upper, date_str, round(strike_window_pct, 2),
                 expirations or "")
    cached = _HIST_GRID_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=43200"
        return cached

    contracts, ts_iso, snapshot_date, data_source, _days = _load_chain_for_historical(
        ticker_upper, requested_date,
    )
    if data_source == "unavailable" or not contracts:
        return _unavailable_envelope(
            ticker_upper,
            f"no EOD chain at or before {date_str} within the lookup window",
        )

    exp_filter = [e.strip() for e in expirations.split(",")] if expirations else None
    summary = gamma.build_grid_summary(
        ticker_upper,
        snapshot_date.isoformat() if snapshot_date else date_str,
        contracts,
        snapshot_ts=ts_iso,
        data_source=data_source,
        window_pct=strike_window_pct,
        expirations_filter=exp_filter,
    )
    payload = summary.to_dict()
    _HIST_GRID_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=43200"
    return payload


# ─── /nodes endpoints (semantic taxonomy) ──────────────────────────────────


def _is_third_friday(d: date_type) -> bool:
    """Third Friday of the month — the standard monthly OPEX date."""
    if d.weekday() != 4:   # Friday
        return False
    # Third Friday falls in days 15-21 inclusive
    return 15 <= d.day <= 21


def _opex_tag(expiration: str) -> bool:
    """Tag cells whose expiration date is a third Friday of its month
    (the canonical monthly OPEX). Weekly Friday expirations and
    Wednesday/Monday expiries are NOT tagged."""
    try:
        ed = date_type.fromisoformat(expiration[:10])
    except (ValueError, TypeError):
        return False
    return _is_third_friday(ed)


def _build_nodes_payload(
    ticker: str, contracts: list[dict], ts_iso: Optional[str],
    snapshot_date: Optional[date_type], data_source: str,
    strike_window_pct: float,
) -> dict:
    """Transform the chain into the trader-facing taxonomy:
    spot / flip / regime / king / gates / midpoints / hedge_nodes /
    opex_nodes / tactical_summary (placeholder until Phase D).

    Hedge node detection (event-window correlation against
    economic_events) is deferred to Phase D — `hedge_nodes` is an
    empty array here. OPEX node tagging is mechanical (third-Friday
    date check) so it ships in B1.
    """
    # Reuse the 1-D summary for King/Gate/Spot/Flip classification
    summary_1d = gamma.build_summary(
        ticker,
        snapshot_date.isoformat() if snapshot_date else "",
        contracts,
        window_pct=strike_window_pct,
    )

    # And the 2-D grid for the OPEX / per-cell context
    grid = gamma.build_grid_summary(
        ticker,
        snapshot_date.isoformat() if snapshot_date else "",
        contracts,
        snapshot_ts=ts_iso,
        data_source=data_source,
        window_pct=strike_window_pct,
    )

    # OPEX nodes — group grid cells whose expiration is a third Friday,
    # one entry per (strike, expiration) cell.
    opex_nodes = [
        {
            "strike": c.strike,
            "expiration": c.expiration,
            "dte": c.dte,
            "gex": c.gex,
            "call_oi": c.call_oi,
            "put_oi": c.put_oi,
        }
        for c in grid.cells if _opex_tag(c.expiration)
    ]

    def _level_to_dict(lv) -> dict:
        # gamma.Level is a dataclass; expose call/put OI + distance
        d = {
            "strike": lv.strike,
            "gex": lv.gex,
            "net_gamma": lv.net_gamma,
            "call_oi": int(lv.call_oi),
            "put_oi": int(lv.put_oi),
            "distance_pct": lv.distance_pct,
            "score": lv.score,
            "dominant_side": "call" if lv.call_oi > lv.put_oi else (
                "put" if lv.put_oi > lv.call_oi else "neutral"
            ),
        }
        return d

    # The 1-D `kings` list may have multiple entries above the King threshold;
    # the conventional "the King" is the largest |GEX| of those, which is
    # also the highest-scored one.
    king = None
    if summary_1d.kings:
        top = max(summary_1d.kings, key=lambda lv: abs(lv.gex))
        king = _level_to_dict(top)

    gates = [_level_to_dict(lv) for lv in summary_1d.gates]
    midpoints: list[dict] = []  # 1-D summary doesn't yet surface midpoints
                                # via build_summary; defer to Phase D.

    return {
        "ticker": ticker.upper(),
        "snapshot_ts": ts_iso,
        "snapshot_date": (snapshot_date.isoformat() if snapshot_date else None),
        "data_source": data_source,
        "spot": {
            "price": summary_1d.spot.price,
            "method": summary_1d.spot.method,
            "note": summary_1d.spot.note,
        } if summary_1d.spot.price > 0 else None,
        "gamma_balance": summary_1d.gamma_balance,
        "gamma_flip": summary_1d.gamma_flip,
        "regime": summary_1d.regime,
        "total_gex": summary_1d.total_gex,
        "total_vex": grid.total_vex,
        "king": king,
        "gates": gates,
        "midpoints": midpoints,
        "hedge_nodes": [],          # Phase D — needs economic_events join
        "opex_nodes": opex_nodes,
        "tactical_summary": None,   # Phase D — wires AI insight pipeline
        "warnings": list(summary_1d.warnings),
    }


@router.get("/api/options/{ticker}/nodes")
async def get_nodes_live(
    ticker: str,
    response: Response,
    strike_window_pct: float = Query(8.0, ge=0.5, le=50.0),
):
    """Live semantic taxonomy — King / Gates / Midpoints / Hedge Nodes /
    OPEX Nodes / Flip / Regime."""
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    cache_key = (ticker_upper, round(strike_window_pct, 2))
    cached = _NODES_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
        return cached

    contracts, ts_iso, snapshot_date, data_source, _ = _load_chain_for_live(ticker_upper)
    if data_source == "unavailable" or not contracts:
        return {
            "ticker": ticker_upper,
            "snapshot_ts": None,
            "snapshot_date": None,
            "data_source": "unavailable",
            "spot": None,
            "gamma_balance": None,
        "gamma_flip": None,
            "regime": "unknown",
            "total_gex": 0.0,
            "total_vex": 0.0,
            "king": None,
            "gates": [],
            "midpoints": [],
            "hedge_nodes": [],
            "opex_nodes": [],
            "tactical_summary": None,
            "warnings": [
                "no realtime or EOD chain found within the lookup window",
            ],
        }

    payload = _build_nodes_payload(
        ticker_upper, contracts, ts_iso, snapshot_date,
        data_source, strike_window_pct,
    )
    _NODES_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=60"
    return payload


@router.get("/api/options/{ticker}/{date_str}/nodes")
async def get_nodes_historical(
    ticker: str,
    date_str: str,
    response: Response,
    strike_window_pct: float = Query(8.0, ge=0.5, le=50.0),
):
    """Historical semantic taxonomy — EOD only."""
    ticker_upper = _validate_ticker(ticker)
    requested_date = _validate_date(date_str)
    _require_cloud_sql()

    cache_key = (ticker_upper, date_str, round(strike_window_pct, 2))
    cached = _HIST_NODES_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=43200"
        return cached

    contracts, ts_iso, snapshot_date, data_source, _ = _load_chain_for_historical(
        ticker_upper, requested_date,
    )
    if data_source == "unavailable" or not contracts:
        return {
            "ticker": ticker_upper,
            "snapshot_ts": None,
            "snapshot_date": None,
            "data_source": "unavailable",
            "spot": None,
            "gamma_balance": None,
        "gamma_flip": None,
            "regime": "unknown",
            "total_gex": 0.0,
            "total_vex": 0.0,
            "king": None,
            "gates": [],
            "midpoints": [],
            "hedge_nodes": [],
            "opex_nodes": [],
            "tactical_summary": None,
            "warnings": [
                f"no EOD chain at or before {date_str} within the lookup window",
            ],
        }

    payload = _build_nodes_payload(
        ticker_upper, contracts, ts_iso, snapshot_date,
        data_source, strike_window_pct,
    )
    _HIST_NODES_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=43200"
    return payload


# ─── /grid/timeseries endpoint (Phase B2 — realtime only) ──────────────────


_TIMESERIES_CACHE: TTLCache = TTLCache(maxsize=128, ttl=60)


@router.get("/api/options/{ticker}/grid/timeseries")
async def get_grid_timeseries(
    ticker: str,
    response: Response,
    strikes: Optional[str] = Query(
        None,
        description=(
            "Comma-separated strikes (e.g. '650,655,660'). When omitted, "
            "the endpoint picks the top 10 by |GEX| at the most recent snapshot."
        ),
    ),
    expiration: Optional[str] = Query(
        None,
        description=(
            "Single ISO-date expiration (e.g. '2026-06-19'). When omitted, "
            "uses the nearest upcoming expiration to today."
        ),
    ),
    lookback_hours: float = Query(
        1.0, ge=0.0833, le=6.5,
        description="How far back to fetch snapshots (max 6.5h = one RTH session).",
    ),
):
    """Per-strike GEX time-series for a single expiration over the last
    N hours of realtime snapshots. Powers the rate-of-change ("Pivot
    Velocity" / "Pivot Build") sparklines in the right panel of the
    heatmap UI.

    Realtime-only by design — there's exactly ONE snapshot per day for
    the EOD path, so a "timeseries" against EOD reduces to a single
    point. If historical day-over-day evolution is needed for a past
    date, a separate /grid/daily-history endpoint can ship in a future
    phase.

    Returns `{ticker, expiration, lookback_hours, data_source, series}`
    where `series` is a list of `{snapshot_ts, strike, gex, delta_from_prev}`
    rows sorted ASC by (snapshot_ts, strike). `delta_from_prev` is the
    change in GEX from the immediately-prior snapshot at the same strike
    (null on the earliest snapshot for that strike).

    Cached 60 s — matches the realtime fetcher's 5-min cadence; no
    point caching longer than the underlying data refreshes.
    """
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    if lookback_hours <= 0:
        raise HTTPException(status_code=400, detail="lookback_hours must be > 0")

    cache_key = (ticker_upper, strikes or "", expiration or "",
                 round(lookback_hours, 3))
    cached = _TIMESERIES_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
        return cached

    from gcp.database import query_to_dataframe

    # Pull snapshots in the lookback window. Filter to a single expiration
    # at the SQL level if specified, otherwise resolve below.
    cutoff = datetime.now(timezone.utc) - pd.Timedelta(hours=lookback_hours)
    where_exp = "AND expiration = :exp" if expiration else ""
    sql = f"""
        SELECT snapshot_ts, snapshot_date, expiration, strike, option_type,
               open_interest, gamma, vega
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND market_session = 'REALTIME'
          AND snapshot_ts >= :cutoff
          {where_exp}
        ORDER BY snapshot_ts, expiration, strike
    """
    params: dict = {"ticker": ticker_upper, "cutoff": cutoff}
    if expiration:
        params["exp"] = expiration

    df = query_to_dataframe(sql, params)
    if df.empty:
        payload = {
            "ticker": ticker_upper,
            "expiration": expiration,
            "lookback_hours": lookback_hours,
            "data_source": "unavailable",
            "series": [],
            "warnings": [
                f"no realtime rows for {ticker_upper} in the last "
                f"{lookback_hours}h "
                + ("(expiration filter applied)" if expiration else "")
            ],
        }
        return payload

    # Resolve expiration: if not specified, pick the nearest upcoming.
    # The expirations column carries datetime.date or pd.Timestamp;
    # normalize to ISO.
    def _exp_iso(v) -> str:
        if hasattr(v, "isoformat"):
            return v.isoformat()[:10]
        return str(v)[:10]

    df["expiration_iso"] = df["expiration"].map(_exp_iso)

    if not expiration:
        today = date_type.today()
        all_exps = sorted({e for e in df["expiration_iso"].unique()})
        upcoming = [e for e in all_exps
                    if date_type.fromisoformat(e) >= today]
        if not upcoming:
            # All cached expirations have already expired — fall back to
            # the most recent past one (still useful for short lookbacks).
            chosen_exp = all_exps[-1] if all_exps else None
        else:
            chosen_exp = upcoming[0]
        if chosen_exp is None:
            return {
                "ticker": ticker_upper,
                "expiration": None,
                "lookback_hours": lookback_hours,
                "data_source": "unavailable",
                "series": [],
                "warnings": ["no expirations in fetched window"],
            }
        df = df[df["expiration_iso"] == chosen_exp]
        expiration = chosen_exp

    # Pick the strike set: explicit list, or top-10 by |GEX| at the
    # most recent snapshot in the window.
    if strikes:
        try:
            strike_set = {float(s.strip()) for s in strikes.split(",") if s.strip()}
        except ValueError as exc:
            # ?strikes=abc or ?strikes=100,xyz → typed 4xx instead of an
            # internal 500. Surface the specific bad token so the caller
            # can fix it (Codex review on PR #544).
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid `strikes` parameter — expected comma-separated "
                    f"numbers (e.g. '650,655,660'). Parse error: {exc}"
                ),
            )
        if not strike_set:
            raise HTTPException(
                status_code=400,
                detail="Invalid `strikes` parameter — empty after parsing",
            )
    else:
        # Use the latest snapshot's per-strike net_gamma magnitude to rank.
        latest_ts = df["snapshot_ts"].max()
        df_latest = df[df["snapshot_ts"] == latest_ts]
        # Aggregate to per-strike net_gamma (calls add, puts subtract)
        agg = (
            df_latest.assign(
                signed_gamma_oi=lambda d: d.apply(
                    lambda r: float(r["gamma"] or 0) * float(r["open_interest"] or 0)
                    * (1 if r["option_type"] == "calls" else -1),
                    axis=1,
                ),
            )
            .groupby("strike")["signed_gamma_oi"]
            .sum()
            .abs()
            .nlargest(10)
        )
        strike_set = set(agg.index.tolist())

    df = df[df["strike"].isin(strike_set)]
    if df.empty:
        return {
            "ticker": ticker_upper,
            "expiration": expiration,
            "lookback_hours": lookback_hours,
            "data_source": "unavailable",
            "series": [],
            "warnings": [
                f"no rows match strikes={sorted(strike_set)} for "
                f"expiration={expiration}"
            ],
        }

    # Per-snapshot per-strike net GEX (we need spot to compute dollar
    # notional — use the latest snapshot's parity-derived spot as a
    # stable reference across the lookback window. Spot doesn't move
    # enough in 1 hour to materially distort the time series).
    latest_contracts = _df_to_contracts(df[df["snapshot_ts"] == df["snapshot_ts"].max()])
    spot_est = gamma.estimate_spot(latest_contracts)
    spot = spot_est.price if spot_est.price > 0 else 100.0  # safe default

    # Aggregate per (snapshot_ts, strike) → signed gamma × OI, then GEX
    rows = []
    for ts in sorted(df["snapshot_ts"].unique()):
        snap = df[df["snapshot_ts"] == ts]
        # Per-strike signed net gamma
        for strike in sorted(strike_set):
            cell = snap[snap["strike"] == strike]
            if cell.empty:
                continue
            net_g = sum(
                float(r["gamma"] or 0) * float(r["open_interest"] or 0)
                * (1 if r["option_type"] == "calls" else -1)
                for _, r in cell.iterrows()
            )
            gex = net_g * spot * spot * gamma.GEX_MULTIPLIER
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rows.append({
                "snapshot_ts": ts_iso,
                "strike": float(strike),
                "gex": gex,
                "delta_from_prev": None,  # filled below
            })

    # Per-strike delta_from_prev — single pass after sort.
    by_strike: dict[float, float] = {}
    for r in rows:
        prev = by_strike.get(r["strike"])
        r["delta_from_prev"] = (r["gex"] - prev) if prev is not None else None
        by_strike[r["strike"]] = r["gex"]

    payload = {
        "ticker": ticker_upper,
        "expiration": expiration,
        "lookback_hours": lookback_hours,
        "data_source": "realtime",
        "strikes_resolved": sorted(strike_set),
        "spot_used": spot,
        "spot_method": spot_est.method,
        "series": rows,
    }
    _TIMESERIES_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=60"
    return payload
