"""
Options flow router — Cloud SQL reader over etf_options_snapshots (AlphaVantage EOD).

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
import re
from datetime import date, datetime
from pathlib import Path
import sys

import math

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
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
               snapshot_ts
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

    # Take the max snapshot_ts as the "as of" marker.
    snapshot_ts_val = df["snapshot_ts"].max() if "snapshot_ts" in df.columns else None
    if isinstance(snapshot_ts_val, (pd.Timestamp, datetime)):
        snapshot_timestamp = snapshot_ts_val.isoformat()
    else:
        snapshot_timestamp = date_str

    response = {
        "ticker": ticker_upper,
        "date": date_str,
        "options": contracts,
        "snapshot_timestamp": snapshot_timestamp,
        "metadata": {
            "source": "cloud_sql",
            "data_source": "alphavantage",
            "row_count": len(contracts),
        },
    }
    _CHAIN_CACHE[cache_key] = response
    return {**response, "cached": False}


# ── Greeks + Nodes (canonical compute, single source of truth) ──────────────
#
# The frontend used to run this math in TypeScript (greeksCalculator.ts,
# nodeAnalyzer.ts). That meant every tuning change had to be replicated in
# two languages. These endpoints consolidate the math server-side — the
# frontend posts the chain + spot and receives computed metrics.

# Config constants — if we ever want to tune these per-ticker or per-strategy,
# move them into a config table. For now they mirror the values used by the
# original heatseeker implementation.
SPOT_MULTIPLIER = 100
GEX_MULTIPLIER = 0.01
VEX_MULTIPLIER = 0.01
ATM_TOLERANCE = 0.02           # 2% band used for implied-move vega avg
NODE_MIN_GAMMA = 500.0         # absolute net-gamma floor for "significant"
NODE_TOP_COUNT = 5             # king + gatekeepers
MIDPOINT_RATIO = 0.5           # gamma balance band for midpoint detection
DEFAULT_STRIKE_RANGE_PCT = 0.15  # ±15% display range around spot


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


def _aggregate_by_strike(options: list[_OptionRecord]) -> list[dict]:
    """Group the chain by strike and net gamma (calls positive, puts negative)."""
    agg: dict[float, dict] = {}
    for opt in options:
        s = opt.strike
        if s not in agg:
            agg[s] = {
                "strike": s,
                "net_gamma": 0.0,
                "call_gamma": 0.0,
                "put_gamma": 0.0,
                "call_oi": 0.0,
                "put_oi": 0.0,
                "call_volume": 0.0,
                "put_volume": 0.0,
            }
        gamma_oi = (opt.gamma or 0.0) * (opt.open_interest or 0.0)
        if opt.type == "call":
            agg[s]["call_gamma"] += gamma_oi
            agg[s]["call_oi"] += opt.open_interest or 0.0
            agg[s]["call_volume"] += opt.volume or 0.0
            agg[s]["net_gamma"] += gamma_oi
        else:
            agg[s]["put_gamma"] += gamma_oi
            agg[s]["put_oi"] += opt.open_interest or 0.0
            agg[s]["put_volume"] += opt.volume or 0.0
            agg[s]["net_gamma"] -= gamma_oi
    return sorted(agg.values(), key=lambda r: r["strike"])


def _gex_by_strike(strikes: list[dict], spot: float) -> list[dict]:
    spot_sq = spot * spot
    return [
        {
            "strike": s["strike"],
            "gex": s["net_gamma"] * spot_sq * GEX_MULTIPLIER,
            "call_gex": s["call_gamma"] * spot_sq * GEX_MULTIPLIER,
            "put_gex": -s["put_gamma"] * spot_sq * GEX_MULTIPLIER,
        }
        for s in strikes
    ]


def _total_gex(options: list[_OptionRecord], spot: float) -> float:
    spot_sq = spot * spot
    total = 0.0
    for o in options:
        if not o.gamma or not o.open_interest:
            continue
        dealer_gamma = -o.gamma
        total += dealer_gamma * o.open_interest * SPOT_MULTIPLIER * spot_sq * GEX_MULTIPLIER
    return total


def _total_vex(options: list[_OptionRecord], spot: float) -> float:
    total = 0.0
    for o in options:
        if not o.vega or not o.open_interest:
            continue
        dealer_vanna = -o.vega
        total += dealer_vanna * o.open_interest * SPOT_MULTIPLIER * spot * VEX_MULTIPLIER
    return total


def _zero_gamma(strikes: list[dict]) -> float | None:
    for i in range(len(strikes) - 1):
        g1 = strikes[i]["net_gamma"]
        g2 = strikes[i + 1]["net_gamma"]
        if g1 * g2 < 0:
            s1 = strikes[i]["strike"]
            s2 = strikes[i + 1]["strike"]
            return s1 + (0 - g1) * (s2 - s1) / (g2 - g1)
    return None


def _max_pain(strikes: list[dict]) -> float | None:
    if not strikes:
        return None
    min_pain = math.inf
    best = strikes[0]["strike"]
    for target in strikes:
        pain = 0.0
        for s in strikes:
            pain += max(0.0, target["strike"] - s["strike"]) * s["call_oi"]
            pain += max(0.0, s["strike"] - target["strike"]) * s["put_oi"]
        if pain < min_pain:
            min_pain = pain
            best = target["strike"]
    return best


def _implied_move(options: list[_OptionRecord], spot: float) -> float | None:
    atm = [o for o in options if abs(o.strike - spot) / spot < ATM_TOLERANCE]
    if not atm:
        return None
    vegas = [o.vega for o in atm if o.vega is not None]
    if not vegas:
        return None
    avg_vega = sum(vegas) / len(vegas)
    return avg_vega * math.sqrt(252) * spot * 0.01


def _detect_nodes(strikes: list[dict], spot: float) -> dict:
    significant = [s for s in strikes if abs(s["net_gamma"]) >= NODE_MIN_GAMMA]
    if not significant:
        return {"kingNode": None, "gatekeepers": [], "midpoints": [], "allNodes": []}

    by_gamma = sorted(significant, key=lambda r: abs(r["net_gamma"]), reverse=True)

    def _node(s: dict, node_type: str) -> dict:
        return {
            "type": node_type,
            "strike": s["strike"],
            "gamma": s["net_gamma"],
            "distance_from_spot": s["strike"] - spot,
            "distance_percent": ((s["strike"] - spot) / spot) * 100,
        }

    king = _node(by_gamma[0], "king")
    gatekeepers = [_node(s, "gatekeeper") for s in by_gamma[1:NODE_TOP_COUNT]]

    midpoints: list[dict] = []
    for i in range(len(by_gamma) - 1):
        cur = by_gamma[i]
        nxt = by_gamma[i + 1]
        if cur["net_gamma"] * nxt["net_gamma"] < 0 and nxt["net_gamma"] != 0:
            ratio = abs(cur["net_gamma"] / nxt["net_gamma"])
            if MIDPOINT_RATIO <= ratio <= (1 / MIDPOINT_RATIO):
                mid_strike = (cur["strike"] + nxt["strike"]) / 2
                midpoints.append({
                    "type": "midpoint",
                    "strike": mid_strike,
                    "gamma": 0.0,
                    "distance_from_spot": mid_strike - spot,
                    "distance_percent": ((mid_strike - spot) / spot) * 100,
                    "lower_bound": min(cur["strike"], nxt["strike"]),
                    "upper_bound": max(cur["strike"], nxt["strike"]),
                })

    all_nodes = [king] + gatekeepers + midpoints
    return {
        "kingNode": king,
        "gatekeepers": gatekeepers,
        "midpoints": midpoints,
        "allNodes": all_nodes,
    }


@router.post("/api/options/greeks")
def compute_options_greeks(req: _GreeksRequest) -> dict:
    """Single source of truth for GEX/VEX/max-pain/implied-move/nodes.

    The frontend previously computed all of this in TypeScript. Centralizing
    it here means config tweaks (multipliers, thresholds) change in one place.
    """
    if req.spot_price <= 0 or not req.options:
        empty = {
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
            "config": {
                "strike_range_pct": req.strike_range_pct or DEFAULT_STRIKE_RANGE_PCT,
                "atm_tolerance": ATM_TOLERANCE,
                "node_min_gamma": NODE_MIN_GAMMA,
            },
        }
        return empty

    aggregated = _aggregate_by_strike(req.options)
    gex_by_strike = _gex_by_strike(aggregated, req.spot_price)

    calls = [o for o in req.options if o.type == "call"]
    puts = [o for o in req.options if o.type == "put"]
    call_oi = sum(o.open_interest or 0.0 for o in calls)
    put_oi = sum(o.open_interest or 0.0 for o in puts)

    metrics = {
        "total_gex": _total_gex(req.options, req.spot_price),
        "total_vex": _total_vex(req.options, req.spot_price),
        "zero_gamma": _zero_gamma(aggregated),
        "max_pain": _max_pain(aggregated),
        "implied_move": _implied_move(req.options, req.spot_price),
        "put_call_ratio": (put_oi / call_oi) if call_oi > 0 else 0.0,
    }

    nodes = _detect_nodes(aggregated, req.spot_price)

    return {
        "aggregated": aggregated,
        "gex_by_strike": gex_by_strike,
        "metrics": metrics,
        "nodes": nodes,
        "config": {
            "strike_range_pct": req.strike_range_pct or DEFAULT_STRIKE_RANGE_PCT,
            "atm_tolerance": ATM_TOLERANCE,
            "node_min_gamma": NODE_MIN_GAMMA,
        },
    }
