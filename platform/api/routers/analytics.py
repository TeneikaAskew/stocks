"""
Analytics router — trade stats computed server-side.

Two endpoints:

    POST /api/analytics/trade-stats
        Compute summary stats (win rate, profit factor, avg win/loss, max
        win/loss) for an ad-hoc list of trades. Used by ChartsPage for its
        in-memory annotation trades — the math lives here so it matches
        any server-side aggregation, not a duplicate TS formula.

    GET /api/analytics/summary/{ticker}?days=N
        Read the real ``trades`` table in Cloud SQL for `ticker`, filter to
        the last `days` days (default 90), and return the same shape as
        POST. Useful for Dashboard KPIs and the Insights backtest section.
"""
from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _HAS_CLOUD_SQL = is_cloud_sql_configured()
except Exception:  # pragma: no cover - import guard
    _HAS_CLOUD_SQL = False
    query_to_dataframe = None  # type: ignore[assignment]

log = logging.getLogger(__name__)
router = APIRouter()


# ── Shapes ──────────────────────────────────────────────────────────────────

class _TradeIn(BaseModel):
    # Ephemeral trades from ChartsPage annotations. Status maps directly.
    status: str                      # 'active' | 'win' | 'loss'
    pnl: float | None = None
    optionType: str | None = None    # 'CALL' | 'PUT'


class _TradeStatsRequest(BaseModel):
    trades: list[_TradeIn]


class _TradeStats(BaseModel):
    totalTrades: int
    closedTrades: int
    activeTrades: int
    winCount: int
    lossCount: int
    winRate: float
    totalPnL: float
    avgPnL: float
    maxWin: float
    maxLoss: float
    profitFactor: float | None   # None when no closed trades; Infinity-safe via JSON-friendly null
    callCount: int
    putCount: int


def _compute_stats(items: list[dict]) -> _TradeStats:
    """Shared aggregator — used by both endpoints so the math is identical."""
    total = len(items)
    closed = [t for t in items if t.get("status") in ("win", "loss")]
    wins = [t for t in closed if t["status"] == "win"]
    losses = [t for t in closed if t["status"] == "loss"]
    active = [t for t in items if t.get("status") == "active"]

    def _pnl(t: dict) -> float:
        v = t.get("pnl")
        return float(v) if isinstance(v, (int, float)) else 0.0

    pnls = [_pnl(t) for t in closed]
    win_pnls = [_pnl(t) for t in wins]
    loss_pnls = [abs(_pnl(t)) for t in losses]

    total_wins = sum(win_pnls)
    total_losses = sum(loss_pnls)

    # profit_factor: gross profit / gross loss. When both are zero or no
    # closed trades, return None (the frontend renders "--"). When only
    # losses are zero but wins > 0, we call that "undefined" (None) rather
    # than +Infinity because Infinity doesn't JSON-serialize.
    if total_losses > 0:
        profit_factor: float | None = total_wins / total_losses
    else:
        profit_factor = None

    return _TradeStats(
        totalTrades=total,
        closedTrades=len(closed),
        activeTrades=len(active),
        winCount=len(wins),
        lossCount=len(losses),
        winRate=(len(wins) / len(closed) * 100.0) if closed else 0.0,
        totalPnL=sum(pnls),
        avgPnL=(sum(pnls) / len(pnls)) if pnls else 0.0,
        maxWin=max(win_pnls) if win_pnls else 0.0,
        maxLoss=max(loss_pnls) if loss_pnls else 0.0,
        profitFactor=profit_factor,
        callCount=sum(1 for t in items if t.get("optionType") == "CALL"),
        putCount=sum(1 for t in items if t.get("optionType") == "PUT"),
    )


# ── POST /api/analytics/trade-stats ─────────────────────────────────────────

@router.post("/api/analytics/trade-stats", response_model=_TradeStats)
def compute_trade_stats(req: _TradeStatsRequest) -> _TradeStats:
    items = [t.model_dump() for t in req.trades]
    return _compute_stats(items)


# ── GET /api/analytics/summary/{ticker} ─────────────────────────────────────

@router.get("/api/analytics/summary/{ticker}", response_model=_TradeStats)
def get_trade_summary(ticker: str, days: int = Query(90, ge=1, le=3650)) -> _TradeStats:
    """Summarize rows from the ``trades`` table for a ticker.

    Uses ``return_pct`` to classify wins/losses and treats ``return_pct`` as
    the per-trade PnL proxy (since the table doesn't store dollar PnL —
    backtested trades use the percent return as the comparable unit).
    """
    ticker_upper = ticker.upper()
    if not _HAS_CLOUD_SQL or query_to_dataframe is None:
        raise HTTPException(
            status_code=503,
            detail="Cloud SQL not configured; cannot query trades table.",
        )

    sql = """
        SELECT direction, return_pct, exit_time, entry_time
        FROM trades
        WHERE ticker = :ticker
          AND entry_time >= NOW() - make_interval(days => :days)
    """
    df = query_to_dataframe(sql, {"ticker": ticker_upper, "days": days})
    if df.empty:
        return _compute_stats([])

    items: list[dict] = []
    for _, row in df.iterrows():
        ret = row.get("return_pct")
        exit_t = row.get("exit_time")
        closed = exit_t is not None and not (isinstance(ret, float) and math.isnan(ret))
        if not closed:
            status = "active"
            pnl = None
        else:
            pnl = float(ret)
            status = "win" if pnl > 0 else "loss"
        opt_type = str(row.get("direction") or "").upper() or None
        items.append({"status": status, "pnl": pnl, "optionType": opt_type})

    return _compute_stats(items)
