"""Strat-history router — per-ticker historical Strat tape + upcoming setup.

GET /api/strat/history/{ticker}
    ?timeframes=1d,1w,1mo,1q   (default daily/weekly/monthly/quarterly)
    &lookback=20               (completed bars per timeframe)

Powers the ticker-list → "all the previous strat for this ticker" panel.
Deterministic, rules-based (lib.strat.StratClassifier) — classifies every
completed bar (candle 1/2U/2D/3 + combo incl. 1-3-1) and describes the
in-progress period's break setup (trigger lines + 2U/2D continuation vs
reversal read). Reads daily bars from Cloud SQL via DataLoader and resamples
up; no new tables.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.strat import compute_strat_history, STRAT_HISTORY_TIMEFRAMES  # noqa: E402

router = APIRouter()
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_VALID_TFS = ("1d", "1w", "1mo", "1q")


@router.get("/api/strat/history/{ticker}")
async def get_strat_history(
    ticker: str,
    timeframes: Optional[str] = Query(
        None, description="comma-separated subset of 1d,1w,1mo,1q"),
    lookback: int = Query(20, ge=1, le=500,
                          description="completed bars per timeframe"),
):
    """Return the historical Strat classification per timeframe + upcoming setup."""
    tkr = ticker.upper().strip()
    if not _TICKER_RE.match(tkr):
        raise HTTPException(status_code=400, detail=f"invalid ticker: {ticker!r}")

    if timeframes:
        tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
        bad = [t for t in tfs if t not in _VALID_TFS]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"invalid timeframe(s) {bad}; valid: {list(_VALID_TFS)}")
    else:
        tfs = list(STRAT_HISTORY_TIMEFRAMES)

    try:
        result = compute_strat_history(tkr, timeframes=tfs, lookback=lookback)
    except Exception as exc:  # data-access / compute failure → surface, don't fake
        logger.exception("strat history failed for %s", tkr)
        raise HTTPException(status_code=502,
                            detail=f"failed to compute strat history for {tkr}: {exc}")

    if not result.get("available"):
        raise HTTPException(status_code=404,
                            detail=result.get("reason", f"no strat history for {tkr}"))
    return result
