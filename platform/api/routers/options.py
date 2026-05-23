"""
Options flow router — Cloud SQL reader over etf_options_snapshots.

As of 2026-05-22 (Track 0 of the realtime-options multi-track plan, see
docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md) the table holds both
nightly EOD snapshots and 5-minute REALTIME snapshots — both surface via
the same endpoints; the `market_session` field on each response tells
the caller which kind they got.

Endpoints
---------
GET /api/options/dates/{ticker}
    Returns up to 1000 most recent snapshot dates that actually have AlphaVantage
    data in Cloud SQL. Never fabricates weekdays. Result is in descending order
    (newest first).

GET /api/options/{ticker}/{date_str}
    Returns the normalized option chain for a given ticker and snapshot date.
    Reads Cloud SQL only — no live AlphaVantage proxy on the request path.
    Data is ingested by `gcp.fetchers.fetch_av_historical_options` via the
    daily GitHub Actions workflow.

GET /api/options/live/{ticker}/{date_str}
    Live AlphaVantage HISTORICAL_OPTIONS proxy. Replaces the decommissioned
    Cloudflare Worker (options-heatseeker/worker.js). Used by the React page
    as a fallback when Cloud SQL doesn't yet have rows for the requested
    snapshot (e.g. today's intraday chain before the 9 PM EOD fetcher runs).
    Response shape is identical to GET /api/options/{ticker}/{date_str}.

Design notes
------------
* Data source: `etf_options_snapshots WHERE data_source='alphavantage'`.
  Yahoo-sourced rows (`data_source IS NULL`) are explicitly excluded.
* Cache: cachetools.TTLCache keyed on (ticker, date). EOD rows are immutable
  once written, so cache hit rate approaches 100% after first request each day.
* Response shape is kept identical to the prior live-proxy implementation so
  the React page needs no contract change. Column mapping:
    option_type ('calls'|'puts') → type ('call'|'put')
    last_price                    → last
"""
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
import sys

import math

import httpx
import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

# Project root so we can import gcp.database the same way the journal router does.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _HAS_CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception as _exc:  # pragma: no cover - import-time guard
    _HAS_CLOUD_SQL = False
    logging.getLogger(__name__).warning("Cloud SQL unavailable: %s", _exc)

log = logging.getLogger(__name__)
router = APIRouter()

VALID_TICKERS = {"SPY", "IWM", "QQQ", "SPX"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (ticker, date_str) → response dict; 12h TTL (EOD rows are immutable).
_CHAIN_CACHE: TTLCache = TTLCache(maxsize=512, ttl=43200)
# ticker → list[date_str]; 12h TTL. Dates list only changes once per day when
# the scheduled AV fetcher runs, so long TTL avoids re-running the distinct
# scan on cold caches (which is expensive on db-g1-small without the composite
# (ticker, data_source, snapshot_date) index in place).
_DATES_CACHE: TTLCache = TTLCache(maxsize=16, ttl=43200)
# Live AV proxy cache: (ticker, date_str) → response dict; 5-min TTL.
# Live data is fresher than EOD; the 5-min ceiling bounds AV rate-limit
# exposure on the free tier (5 calls/min, 500/day).
_LIVE_CACHE: TTLCache = TTLCache(maxsize=128, ttl=300)

# AlphaVantage proxy config — mirrors api.routers.live so the env-var
# resolution + endpoint URL stay in lockstep.
_AV_API_KEY = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
_AV_BASE = "https://www.alphavantage.co/query"


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_cloud_sql() -> None:
    if not _HAS_CLOUD_SQL:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloud SQL is not configured for the platform API. "
                "Set CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME and "
                "restart the server."
            ),
        )


def _validate_ticker(ticker: str) -> str:
    ticker_upper = ticker.upper()
    if ticker_upper not in VALID_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker must be one of {sorted(VALID_TICKERS)}, got '{ticker_upper}'",
        )
    return ticker_upper


def _validate_date(date_str: str) -> date:
    if not DATE_RE.match(date_str):
        raise HTTPException(
            status_code=400,
            detail=f"Date must be in YYYY-MM-DD format, got '{date_str}'",
        )
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: '{date_str}'")


# Map Cloud SQL column names → frontend-expected keys. The frontend
# (greeksCalculator.ts) looks for `type: 'call'|'put'`, `strike`, `open_interest`,
# `gamma`, `vega`, `delta`, `volume`, plus a few others for display.
_COLUMN_ALIAS = {
    "last_price": "last",
}

# Columns we surface in each contract row (order not significant for the
# frontend, but kept stable for debugging).
_CONTRACT_COLUMNS = [
    "contract_symbol", "expiration", "strike", "option_type",
    "bid", "ask", "mark", "last_price", "volume", "open_interest",
    "implied_volatility", "delta", "gamma", "theta", "vega", "rho",
]


def _av_to_contracts(rows: list[dict]) -> list[dict]:
    """Convert AlphaVantage HISTORICAL_OPTIONS rows into the same JSON shape
    `_df_to_contracts` produces, so the live endpoint and the Cloud SQL
    endpoint return byte-identical contracts. Frontend code path stays unified.

    AV row keys (verified against the public schema):
        contractID, symbol, type ('call'|'put'), strike, expiration,
        bid, ask, mark, last, volume, open_interest, implied_volatility,
        delta, gamma, theta, vega, rho, date
    All numeric values arrive as strings; we cast to float and drop rows
    missing the core fields the frontend requires (type, strike, expiration).
    """
    if not rows:
        return []

    type_map = {"call": "call", "calls": "call", "put": "put", "puts": "put"}

    def _maybe_float(v):
        if v is None or v == "":
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(f):
            return None
        return f

    def _maybe_int(v):
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    out: list[dict] = []
    for r in rows:
        type_raw = (r.get("type") or "").lower()
        type_val = type_map.get(type_raw)
        strike_val = _maybe_float(r.get("strike"))
        exp_val = r.get("expiration")
        if not type_val or strike_val is None or not exp_val:
            continue
        # Map AV's `contractID` to our `contract_symbol` for display parity
        # with the Cloud SQL row shape.
        contract_symbol = r.get("contractID") or r.get("contract_symbol")
        out.append({
            "contract_symbol": contract_symbol,
            "expiration": str(exp_val),
            "strike": strike_val,
            "type": type_val,
            "bid": _maybe_float(r.get("bid")),
            "ask": _maybe_float(r.get("ask")),
            "mark": _maybe_float(r.get("mark")),
            "last": _maybe_float(r.get("last")),
            "volume": _maybe_int(r.get("volume")),
            "open_interest": _maybe_int(r.get("open_interest")),
            "implied_volatility": _maybe_float(r.get("implied_volatility")),
            "delta": _maybe_float(r.get("delta")),
            "gamma": _maybe_float(r.get("gamma")),
            "theta": _maybe_float(r.get("theta")),
            "vega": _maybe_float(r.get("vega")),
            "rho": _maybe_float(r.get("rho")),
        })
    return out


def _df_to_contracts(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame of etf_options_snapshots rows into the JSON shape the
    React page already consumes.  Handles NaN → None, option_type pluralization,
    and column aliases (`last_price` → `last`).
    """
    if df.empty:
        return []

    # Drop rows with missing core fields the frontend requires.
    df = df.dropna(subset=["option_type", "strike", "expiration"])

    # Plural → singular for `type` field.
    type_map = {"calls": "call", "puts": "put"}

    import math

    records: list[dict] = []
    for row in df.to_dict(orient="records"):
        out: dict = {}
        for col in _CONTRACT_COLUMNS:
            if col not in row:
                continue
            key = _COLUMN_ALIAS.get(col, col)
            val = row[col]
            # NaN → None at the value level. df.where(pd.notnull(df), None)
            # doesn't work for float columns because pandas re-coerces None
            # back to NaN. Must handle it on the dict that goes to json.dumps.
            if isinstance(val, float) and math.isnan(val):
                val = None
            if col == "option_type":
                # Frontend expects `type` (singular value 'call'/'put').
                out["type"] = type_map.get(str(val).lower() if val else "", val)
                continue
            if col == "expiration" and val is not None:
                # Expiration may come back as a datetime/date — normalize to ISO string.
                if hasattr(val, "strftime"):
                    val = val.strftime("%Y-%m-%d")
                else:
                    val = str(val)
            out[key] = val
        records.append(out)
    return records


# ── endpoints ────────────────────────────────────────────────────────────────

# Widening range schedule used by the dates endpoint. The first query tries a
# 60-day window, then 1y, 3y, 10y, unlimited — stopping as soon as we have a
# reasonable number of dates. This keeps the index scan bounded on large tables
# (critical without the composite (ticker, data_source, snapshot_date) index)
# while still returning the full history if the table is small.
_DATES_WINDOW_DAYS = (60, 365, 1100, 3650, None)
_DATES_MIN_RESULTS = 40  # ≈ 2 months of weekdays


@router.get("/api/options/dates/{ticker}")
async def get_options_dates(ticker: str):
    """Return up to 1000 most-recent snapshot dates that have AlphaVantage data
    in Cloud SQL for the given ticker (newest first).

    Uses a widening-range scan: tries a 60-day window first, expanding to 1y,
    3y, 10y, and then unbounded if fewer than 40 dates are found. This keeps
    cold queries bounded when the covering index on (ticker, data_source,
    snapshot_date) isn't yet in place.
    """
    ticker_upper = _validate_ticker(ticker)
    _require_cloud_sql()

    cached = _DATES_CACHE.get(ticker_upper)
    if cached is not None:
        return {"ticker": ticker_upper, "dates": cached, "source": "cloud_sql", "cached": True}

    dates: list[str] = []
    window_used: str | None = None
    for days in _DATES_WINDOW_DAYS:
        if days is None:
            sql = """
                SELECT DISTINCT snapshot_date
                FROM   etf_options_snapshots
                WHERE  ticker = :ticker
                  AND  data_source = 'alphavantage'
                ORDER  BY snapshot_date DESC
                LIMIT  1000
            """
            params = {"ticker": ticker_upper}
            window_used = "unbounded"
        else:
            sql = """
                SELECT DISTINCT snapshot_date
                FROM   etf_options_snapshots
                WHERE  ticker = :ticker
                  AND  data_source = 'alphavantage'
                  AND  snapshot_date >= CURRENT_DATE - make_interval(days => :days)
                ORDER  BY snapshot_date DESC
                LIMIT  1000
            """
            params = {"ticker": ticker_upper, "days": days}
            window_used = f"{days}d"

        df = query_to_dataframe(sql, params)
        if not df.empty:
            dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                     for d in df["snapshot_date"].tolist()]
        if len(dates) >= _DATES_MIN_RESULTS or days is None:
            break

    if not dates:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No AlphaVantage options data ingested for {ticker_upper}. "
                "Run `python -m gcp.fetchers.fetch_av_historical_options` or "
                "trigger the 'Fetch Daily Alpha Vantage Options Data' workflow."
            ),
        )

    _DATES_CACHE[ticker_upper] = dates
    return {
        "ticker": ticker_upper,
        "dates": dates,
        "source": "cloud_sql",
        "window": window_used,
        "cached": False,
    }


@router.get("/api/options/{ticker}/{date_str}")
async def get_options(ticker: str, date_str: str):
    """Return the AlphaVantage option chain for `ticker` on `date_str`
    (YYYY-MM-DD) from Cloud SQL.
    """
    ticker_upper = _validate_ticker(ticker)
    parsed_date = _validate_date(date_str)
    _require_cloud_sql()

    cache_key = (ticker_upper, date_str)
    cached = _CHAIN_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    sql = """
        SELECT contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               snapshot_ts, market_session
        FROM   etf_options_snapshots
        WHERE  ticker = :ticker
          AND  snapshot_date = :snap_date
          AND  data_source = 'alphavantage'
        ORDER  BY expiration, strike, option_type
    """
    df = query_to_dataframe(sql, {"ticker": ticker_upper, "snap_date": parsed_date})

    if df.empty:
        # Look up the nearest available date for a helpful error message.
        nearest_sql = """
            SELECT MAX(snapshot_date) AS nearest
            FROM   etf_options_snapshots
            WHERE  ticker = :ticker
              AND  data_source = 'alphavantage'
              AND  snapshot_date <= :snap_date
        """
        nearest_df = query_to_dataframe(
            nearest_sql, {"ticker": ticker_upper, "snap_date": parsed_date}
        )
        nearest = None
        if not nearest_df.empty and nearest_df.iloc[0]["nearest"] is not None:
            n = nearest_df.iloc[0]["nearest"]
            nearest = n.strftime("%Y-%m-%d") if hasattr(n, "strftime") else str(n)

        msg = (
            f"No AlphaVantage options data for {ticker_upper} on {date_str}. "
            + (f"Most recent available: {nearest}." if nearest
               else "No earlier data ingested for this ticker.")
        )
        raise HTTPException(status_code=404, detail=msg)

    contracts = _df_to_contracts(df)

    # "As-of" marker = freshest snapshot in the result set. When intraday
    # REALTIME and nightly EOD rows coexist for the same snapshot_date, the
    # REALTIME row is strictly newer, so the max() row's market_session is
    # also the correct freshness label for the chain we're returning.
    snapshot_ts_val = None
    market_session_val: str | None = None
    if "snapshot_ts" in df.columns and not df["snapshot_ts"].isna().all():
        idx = df["snapshot_ts"].idxmax()
        snapshot_ts_val = df.at[idx, "snapshot_ts"]
        if "market_session" in df.columns:
            session_raw = df.at[idx, "market_session"]
            market_session_val = (
                str(session_raw) if session_raw is not None and not (
                    isinstance(session_raw, float) and math.isnan(session_raw)
                ) else None
            )

    if isinstance(snapshot_ts_val, (pd.Timestamp, datetime)):
        snapshot_timestamp = snapshot_ts_val.isoformat()
    else:
        snapshot_timestamp = date_str

    response = {
        "ticker": ticker_upper,
        "date": date_str,
        "options": contracts,
        "snapshot_timestamp": snapshot_timestamp,
        "market_session": market_session_val,
        "metadata": {
            "source": "cloud_sql",
            "data_source": "alphavantage",
            "row_count": len(contracts),
        },
    }
    _CHAIN_CACHE[cache_key] = response
    return {**response, "cached": False}


# ── Live AlphaVantage proxy (replaces the decommissioned Cloudflare Worker) ──


@router.get("/api/options/live/{ticker}/{date_str}")
async def get_options_live(ticker: str, date_str: str, response: Response):
    """Fetch the AlphaVantage HISTORICAL_OPTIONS chain live, with the same
    response shape as `/api/options/{ticker}/{date_str}`.

    Used by the React page as a fallback when Cloud SQL doesn't yet have a
    snapshot for the requested date (typically: today's intraday chain
    before the 9 PM EOD fetcher runs). Equivalent to the prior Cloudflare
    Worker at options-heatseeker/worker.js — same validation, error mapping,
    and 5-minute caching, but reading the API key from GCP Secret Manager
    via the AV_API_KEY env var.
    """
    ticker_upper = _validate_ticker(ticker)
    _validate_date(date_str)

    if not _AV_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "AlphaVantage API key not configured. Set AV_API_KEY (or "
                "ALPHA_VANTAGE_API_KEY) in the environment / Secret Manager."
            ),
        )

    cache_key = (ticker_upper, date_str)
    cached = _LIVE_CACHE.get(cache_key)
    if cached is not None:
        # Mirror the Worker's Cache-Control behaviour but tighter (5 min vs 1 hr).
        response.headers["Cache-Control"] = "public, max-age=300"
        return {**cached, "cached": True}

    params = {
        "function": "HISTORICAL_OPTIONS",
        "symbol": ticker_upper,
        "date": date_str,
        "apikey": _AV_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_AV_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="AlphaVantage request timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AlphaVantage request failed: {exc}")

    # Standard AV soft-error envelope checks (identical to live.py).
    if "Note" in data:
        raise HTTPException(status_code=429, detail=f"AlphaVantage rate limit: {data['Note']}")
    if "Information" in data:
        raise HTTPException(status_code=429, detail=f"AlphaVantage limit: {data['Information']}")
    if "Error Message" in data:
        raise HTTPException(status_code=400, detail=f"AlphaVantage error: {data['Error Message']}")

    rows = data.get("data") or []
    contracts = _av_to_contracts(rows)
    if not contracts:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No live options data returned by AlphaVantage for "
                f"{ticker_upper} on {date_str}."
            ),
        )

    payload = {
        "ticker": ticker_upper,
        "date": date_str,
        "options": contracts,
        "snapshot_timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        # The live AV proxy is the freshest possible source (no DB hop); tag
        # it REALTIME so the freshness badge shows green even when this is the
        # 404-fallback path for a date Cloud SQL hasn't ingested yet.
        "market_session": "REALTIME",
        "metadata": {
            "source": "alphavantage_live",
            "data_source": "alphavantage",
            "row_count": len(contracts),
        },
    }
    _LIVE_CACHE[cache_key] = payload
    response.headers["Cache-Control"] = "public, max-age=300"
    return {**payload, "cached": False}


# ── Greeks + Nodes (canonical compute, single source of truth) ──────────────
#
# All math delegates to lib.gamma so the API, AI gamma analyst, CLI, and
# Pine-companion exports share one implementation. See lib/gamma.py for the
# locked sign convention and taxonomy. The /api/options/greeks response
# preserves its existing contract; /api/options/{ticker}/{date}/levels is
# the new chain-source-aware GET that returns the full GammaSummary
# (King/Gate/Spot/Flip taxonomy, regime classification, layered spot
# estimation) without requiring the client to send the chain.

from lib import gamma  # noqa: E402

DEFAULT_STRIKE_RANGE_PCT = gamma.DEFAULT_STRIKE_RANGE_PCT
ATM_TOLERANCE = gamma.ATM_TOLERANCE
NODE_MIN_GAMMA = gamma.NODE_MIN_GAMMA


class _OptionRecord(BaseModel):
    type: str  # 'call' | 'put'
    strike: float
    open_interest: float | None = None
    gamma: float | None = None
    vega: float | None = None
    delta: float | None = None
    volume: float | None = None


class _GreeksRequest(BaseModel):
    options: list[_OptionRecord]
    spot_price: float
    strike_range_pct: float | None = None  # optional display filter


def _opts_to_dicts(options: list[_OptionRecord]) -> list[dict]:
    """Turn pydantic option records into the plain-dict shape lib.gamma accepts."""
    return [o.model_dump() for o in options]


@router.post("/api/options/greeks")
def compute_options_greeks(req: _GreeksRequest) -> dict:
    """Single source of truth for GEX/VEX/max-pain/implied-move/nodes.

    The frontend previously computed all of this in TypeScript. Centralizing
    it here means config tweaks (multipliers, thresholds) change in one place.
    Math lives in lib/gamma.py.
    """
    config = {
        "strike_range_pct": req.strike_range_pct or DEFAULT_STRIKE_RANGE_PCT,
        "atm_tolerance": ATM_TOLERANCE,
        "node_min_gamma": NODE_MIN_GAMMA,
    }

    if req.spot_price <= 0 or not req.options:
        return {
            "aggregated": [],
            "gex_by_strike": [],
            "metrics": {
                "total_gex": 0.0,
                "total_vex": 0.0,
                "zero_gamma": None,
                "max_pain": None,
                "implied_move": None,
                "put_call_ratio": 0.0,
            },
            "nodes": {"kingNode": None, "gatekeepers": [], "midpoints": [], "allNodes": []},
            "config": config,
        }

    opts = _opts_to_dicts(req.options)
    aggregated = gamma.aggregate_by_strike(opts)
    gex_strikes = gamma.gex_by_strike(aggregated, req.spot_price)

    metrics = {
        # Total GEX is summed from per-strike values so the sign is consistent
        # with the per-strike rows the heatmap displays.
        "total_gex": gamma.total_gex_from_strikes(gex_strikes),
        "total_vex": gamma.total_vex(opts, req.spot_price),
        "zero_gamma": gamma.zero_gamma(aggregated),
        "max_pain": gamma.max_pain(aggregated),
        "implied_move": gamma.implied_move(opts, req.spot_price),
        "put_call_ratio": gamma.put_call_ratio(opts),
    }

    nodes = gamma.detect_nodes(aggregated, req.spot_price)

    return {
        "aggregated": aggregated,
        "gex_by_strike": gex_strikes,
        "metrics": metrics,
        "nodes": nodes,
        "config": config,
    }


@router.get("/api/options/{ticker}/{date_str}/levels")
async def get_gamma_levels(
    ticker: str,
    date_str: str,
    window_pct: float = 8.0,
    spot: float | None = None,
):
    """Stratalyst-style King/Gate/Spot/Flip taxonomy for a Cloud SQL snapshot.

    Loads the chain from etf_options_snapshots, runs lib.gamma.build_summary,
    returns the full GammaSummary (spot estimate w/ method, gamma flip,
    regime, classified levels with composite scores, warnings).

    Unlike POST /api/options/greeks (which the heatmap UI uses), this is a
    chain-source-aware GET — useful for the AI gamma analyst, Pine companion
    export, and any client that wants levels without shipping the chain
    upstream. Spot is estimated server-side via put-call parity (with delta
    + median-strike fallbacks); pass ?spot=... to override.
    """
    ticker_upper = _validate_ticker(ticker)
    parsed_date = _validate_date(date_str)
    _require_cloud_sql()

    # Reuse the existing chain endpoint logic to load + normalize the chain.
    chain_response = await get_options(ticker, date_str)
    options = chain_response.get("options", [])

    summary = gamma.build_summary(
        ticker=ticker_upper,
        snapshot_date=date_str,
        options=options,
        spot_override=spot,
        window_pct=window_pct,
    )

    return {
        **summary.to_dict(),
        "snapshot_timestamp": chain_response.get("snapshot_timestamp"),
        "market_session": chain_response.get("market_session"),
        "chain_size": len(options),
    }
