"""
Grid + Nodes router — 2-D strike × expiration heatmap surface.

Endpoints:

  GET /api/options/{ticker}/grid             — live (realtime → EOD fallback)
  GET /api/options/{ticker}/{date}/grid      — historical (EOD archive)
  GET /api/options/{ticker}/nodes            — live, semantic taxonomy
  GET /api/options/{ticker}/{date}/nodes     — historical, semantic taxonomy

Phase B1 of HEATSEEKER_STYLE_GAMMA_PLAN.md. This router exposes the
math from `lib.gamma.build_grid_summary` + `lib.gamma.build_summary`
to the frontend. It reads from `etf_options_snapshots` only — no
on-demand AV fetching, no inline BSM Greeks, no rate-limit middleware
(those land in Phase B2).

Data source contract (Track 1 tiered loader, restated):

  Live mode (no `{date}` in path):
    1. Most recent REALTIME row strictly before `now` →
       data_source = 'realtime'
    2. else most recent EOD row, ≤2 trading days behind →
       data_source = 'eod_fallback'
    3. else 3-5 trading days behind →
       data_source = 'stale_fallback'
    4. else (or no rows) →
       data_source = 'unavailable' (HTTP 200, empty payload)

  Historical mode (`{date}` in path):
    Most recent EOD row with snapshot_date ≤ requested date.
    Never reads realtime — past-date intraday data is meaningless
    unless explicitly requested via `/grid/timeseries` (Phase B2).

Tickers covered automatically:
  - SPY / IWM / QQQ: live realtime via fetch_av_realtime_options.py
  - SPX, NDX, watchlist single names: live EOD-fallback via the nightly
    fetch_av_historical_options.py write
  - Anything else: returns data_source='unavailable' until Phase B2
    adds the on-demand AV dispatch path
"""
from __future__ import annotations

import logging
from datetime import date as date_type, datetime, timezone
from pathlib import Path
import sys
from typing import Optional

import numpy as np
import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query, Response

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
        "flip": None,
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


# ─── /grid endpoints ───────────────────────────────────────────────────────


@router.get("/api/options/{ticker}/grid")
async def get_grid_live(
    ticker: str,
    response: Response,
    strike_window_pct: float = Query(8.0, ge=0.5, le=50.0,
                                      description="Display window around spot in PERCENT"),
    expirations: Optional[str] = Query(None,
                                        description="Comma-separated ISO dates to whitelist"),
):
    """Live 2-D strike × expiration grid.

    Internal routing:
      - SPY / IWM / QQQ → realtime row from `market_session='REALTIME'`
      - Anything else  → EOD-fallback (most recent nightly write)
      - On-demand AV fetch for off-list tickers ships in Phase B2.

    Returns the `GammaGridSummary` JSON shape — see lib.gamma.

    Cached 60 s. Cache headers: public, max-age=60.
    """
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    cache_key = (ticker_upper, round(strike_window_pct, 2), expirations or "")
    cached = _LIVE_GRID_CACHE.get(cache_key)
    if cached is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
        return cached

    contracts, ts_iso, snapshot_date, data_source, _days = _load_chain_for_live(
        ticker_upper,
    )
    if data_source == "unavailable" or not contracts:
        envelope = _unavailable_envelope(
            ticker_upper,
            "no realtime or EOD chain found within the lookup window",
        )
        # Don't cache unavailable responses — operator wants to see
        # the moment data appears, not a stale "no data" reply.
        return envelope

    exp_filter = [e.strip() for e in expirations.split(",")] if expirations else None
    summary = gamma.build_grid_summary(
        ticker_upper,
        snapshot_date.isoformat() if snapshot_date else "",
        contracts,
        snapshot_ts=ts_iso,
        data_source=data_source,
        window_pct=strike_window_pct,
        expirations_filter=exp_filter,
    )
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
        "flip": summary_1d.flip,
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
            "flip": None,
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
            "flip": None,
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
