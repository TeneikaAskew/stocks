"""Earnings router — reads from the frontend data prep mat views.

Data sources (all in Cloud SQL):
  - earnings_event_outcomes (mat view, refreshed weekly Sunday 8pm ET)
  - earnings_ticker_lean    (mat view, refreshed weekly Sunday 8pm ET)
  - earnings_upcoming_with_history (table, refreshed daily 7:30am ET)
  - earnings_options_strategy_insights (PR-B insights grid)
  - earnings_options_strategy_winners  (top-10 named winners)
  - earnings_calibration                (the live calibration row)

All endpoints return a 5-table JOIN's worth of data in <10ms by reading
from the pre-computed mat views instead of joining on every request.

HTTP `Cache-Control` headers are set per endpoint based on how often the
underlying data actually changes. Repeat visits within TTL hit the
browser cache instead of Cloud SQL.

When Cloud SQL isn't configured (local dev without env vars), endpoints
return 503. They never silently return empty data (CLAUDE.md §3.7).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Response

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger(__name__)
router = APIRouter()

# ── Cloud SQL availability ─────────────────────────────────────────────
_CLOUD_SQL = bool(
    os.environ.get('CLOUD_SQL_CONNECTION_NAME')
    and os.environ.get('DB_USER')
)


def _query_or_503(sql: str, params: dict | None = None):
    """Run a Cloud SQL query or return 503 if not configured.

    Caller gets a DataFrame or raises HTTPException(503).
    """
    if not _CLOUD_SQL:
        raise HTTPException(status_code=503,
                            detail='Cloud SQL not configured on this instance')
    from gcp.database import query_to_dataframe
    try:
        df = query_to_dataframe(sql, params or {})
        return df
    except Exception as e:
        log.error('earnings router query failed: %s', e)
        raise HTTPException(status_code=500,
                            detail=f'query failed: {type(e).__name__}')


def _set_cache(response: Response, seconds: int) -> None:
    """Set HTTP Cache-Control. Public so browsers + intermediaries cache."""
    response.headers['Cache-Control'] = f'public, max-age={seconds}'


def _df_to_records(df) -> list[dict]:
    """Convert DataFrame to JSON-safe records (NaN → None, dates → ISO)."""
    if df is None or df.empty:
        return []
    import math
    import pandas as pd
    out = []
    for _, row in df.iterrows():
        rec: dict = {}
        for col, val in row.items():
            if val is None:
                rec[col] = None
            elif isinstance(val, float) and math.isnan(val):
                rec[col] = None
            elif hasattr(val, 'isoformat'):
                rec[col] = val.isoformat()
            elif isinstance(val, (list, tuple)):
                rec[col] = list(val)
            elif pd.isna(val):
                rec[col] = None
            else:
                rec[col] = val
        out.append(rec)
    return out


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/upcoming                                              │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/upcoming')
async def upcoming(
    response: Response,
    days: int = Query(14, ge=1, le=60),
):
    """Next N days of earnings reporters, decorated with full history.

    Reads earnings_upcoming_with_history (refreshed daily 7:30am ET).
    Each row carries: archetype, confidence_label, BOTH recommendation
    modes (long-only + IC), lean stats, and last_3_events JSONB.
    """
    _set_cache(response, 300)  # 5 min
    df = _query_or_503(
        """
        SELECT * FROM earnings_upcoming_with_history
        WHERE refresh_date = (
            SELECT MAX(refresh_date) FROM earnings_upcoming_with_history
        )
          AND earnings_date BETWEEN CURRENT_DATE AND CURRENT_DATE + (:days)::int
        ORDER BY earnings_date, ticker
        """,
        {'days': days},
    )
    return {'rows': _df_to_records(df), 'count': 0 if df is None else len(df)}


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/history/{ticker}                                       │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/history/{ticker}')
async def history(
    ticker: str,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
):
    """Last N quarters for one ticker — full event timeline.

    Reads earnings_event_outcomes. Returns beat/meet/miss, gap%, implied
    vs realized, sustain stats, and which structures historically won
    for THAT event.
    """
    _set_cache(response, 3600)  # 1 hour
    df = _query_or_503(
        """
        SELECT * FROM earnings_event_outcomes
        WHERE ticker = :t
        ORDER BY reported_date DESC
        LIMIT (:limit)::int
        """,
        {'t': ticker.upper(), 'limit': limit},
    )
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f'no events for {ticker.upper()} — try the daily fetcher first',
        )
    return {'ticker': ticker.upper(), 'rows': _df_to_records(df), 'count': len(df)}


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/event/{ticker}/{date}                                  │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/event/{ticker}/{event_date}')
async def event(ticker: str, event_date: str, response: Response):
    """Single-event drill-down."""
    _set_cache(response, 86400)  # 1 day — historical events don't change
    df = _query_or_503(
        """
        SELECT * FROM earnings_event_outcomes
        WHERE ticker = :t AND reported_date = (:d)::date
        """,
        {'t': ticker.upper(), 'd': event_date},
    )
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f'event not found for {ticker.upper()} on {event_date}',
        )
    recs = _df_to_records(df)
    return recs[0]


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/lean                                                   │
# │   Tickers that lean LONG / SHORT — the "find more NVAX" leaderboard │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/lean')
async def lean(
    response: Response,
    direction: Literal['long', 'short', 'all'] = 'all',
    min_quarters: int = Query(4, ge=1, le=40),
    limit: int = Query(50, ge=1, le=500),
):
    """Per-ticker lean leaderboard.

    direction=long  → ORDER BY long_winner_count DESC, lean_score DESC
    direction=short → ORDER BY short_winner_count DESC, lean_score ASC
    direction=all   → ORDER BY total_quarters DESC
    """
    _set_cache(response, 3600)
    if direction == 'long':
        order = 'long_winner_count DESC NULLS LAST, lean_score DESC NULLS LAST'
    elif direction == 'short':
        order = 'short_winner_count DESC NULLS LAST, lean_score ASC NULLS LAST'
    else:
        order = 'total_quarters DESC NULLS LAST'
    df = _query_or_503(
        f"""
        SELECT * FROM earnings_ticker_lean
        WHERE total_quarters >= :mq
        ORDER BY {order}
        LIMIT (:limit)::int
        """,
        {'mq': min_quarters, 'limit': limit},
    )
    return {'rows': _df_to_records(df), 'count': 0 if df is None else len(df)}


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/ticker/{ticker}/lean                                   │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/ticker/{ticker}/lean')
async def ticker_lean(ticker: str, response: Response):
    """Lean stats for one ticker."""
    _set_cache(response, 3600)
    df = _query_or_503(
        "SELECT * FROM earnings_ticker_lean WHERE ticker = :t",
        {'t': ticker.upper()},
    )
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f'no lean stats for {ticker.upper()}',
        )
    return _df_to_records(df)[0]


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/insights/grid                                          │
# │ /api/earnings/insights/winners                                       │
# │ /api/earnings/calibration                                            │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/insights/grid')
async def insights_grid(
    response: Response,
    quintile: Optional[str] = None,
    ratio_bucket: Optional[str] = None,
):
    """The 144-row Q × bucket × structure insights table (PR-B)."""
    _set_cache(response, 3600)
    where = ['calculation_date = (SELECT MAX(calculation_date) FROM earnings_options_strategy_insights)']
    params: dict = {}
    if quintile:
        where.append('quintile = :q'); params['q'] = quintile
    if ratio_bucket:
        where.append('ratio_bucket = :rb'); params['rb'] = ratio_bucket
    df = _query_or_503(
        f"SELECT * FROM earnings_options_strategy_insights "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY quintile, ratio_bucket, structure",
        params,
    )
    return {'rows': _df_to_records(df), 'count': 0 if df is None else len(df)}


@router.get('/api/earnings/insights/winners')
async def insights_winners(
    response: Response,
    structure: Optional[str] = None,
    quintile: str = 'Q5',
    limit: int = Query(10, ge=1, le=100),
):
    """Top-N named winners per (structure × quintile)."""
    _set_cache(response, 3600)
    where = [
        'calculation_date = (SELECT MAX(calculation_date) FROM earnings_options_strategy_winners)',
        'quintile = :q',
    ]
    params: dict = {'q': quintile, 'limit': limit}
    if structure:
        where.append('structure = :s'); params['s'] = structure
    df = _query_or_503(
        f"SELECT * FROM earnings_options_strategy_winners "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY structure, rank "
        f"LIMIT (:limit)::int",
        params,
    )
    return {'rows': _df_to_records(df), 'count': 0 if df is None else len(df)}


@router.get('/api/earnings/calibration')
async def calibration(response: Response):
    """The live calibration row (PR-A + PR-B headline finding)."""
    _set_cache(response, 3600)
    df = _query_or_503(
        "SELECT * FROM earnings_calibration "
        "ORDER BY calibration_date DESC LIMIT 1",
        {},
    )
    if df is None or df.empty:
        raise HTTPException(
            status_code=404, detail='no calibration row found',
        )
    return _df_to_records(df)[0]


# ╭─────────────────────────────────────────────────────────────────────╮
# │ /api/earnings/health/ping — keep-warm target (Scheduler GETs this)  │
# ╰─────────────────────────────────────────────────────────────────────╯

@router.get('/api/earnings/health/ping')
async def health_ping(response: Response):
    """Lightweight warm-up endpoint hit by the keep-warm Cloud Scheduler.

    Returns 200 + a 1-statement Cloud SQL query so the Cloud SQL
    connector (and the FastAPI worker) stay hot during business hours.
    Cache-Control set to 0 so intermediaries never serve a stale 200.
    """
    response.headers['Cache-Control'] = 'no-store'
    if not _CLOUD_SQL:
        return {'status': 'ok', 'db': 'not_configured'}
    try:
        from gcp.database import query_to_dataframe
        query_to_dataframe('SELECT 1 AS ping', {})
        return {'status': 'ok', 'db': 'reachable'}
    except Exception as e:
        log.warning('health/ping db check failed: %s', e)
        return {'status': 'ok', 'db': 'error', 'error': type(e).__name__}
