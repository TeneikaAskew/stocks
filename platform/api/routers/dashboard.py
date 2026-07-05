"""
Dashboard aggregation router.
GET /api/dashboard/brief/{ticker} - Daily bias / strat status from Cloud SQL
GET /api/movement-statement       - PHASE 3 feature-flagged movement read
"""
import os
import sys
import logging
from datetime import datetime, date as _date_cls, timedelta
from pathlib import Path

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

router = APIRouter()
logger = logging.getLogger(__name__)

# Cloud SQL availability (same pattern as main.py)
_CLOUD_SQL = False
_query_fn = None
try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _CLOUD_SQL = is_cloud_sql_configured()
    if _CLOUD_SQL:
        _query_fn = query_to_dataframe
except Exception:
    pass

# Reuse the same holiday calendar / market-open logic as the live router so
# both endpoints agree on what "stale" and "open" mean.
try:
    from platform.api.routers.live import (  # type: ignore[import-not-found]
        _is_market_open,
        get_live_quote,
        ET_TZ,
        MARKET_HOLIDAYS_2026,
    )
except Exception:  # pragma: no cover - import path differs when launched as `api.main`
    try:
        from api.routers.live import (  # type: ignore[no-redef]
            _is_market_open,
            get_live_quote,
            ET_TZ,
            MARKET_HOLIDAYS_2026,
        )
    except Exception:
        _is_market_open = None  # type: ignore[assignment]
        get_live_quote = None  # type: ignore[assignment]
        ET_TZ = None  # type: ignore[assignment]
        MARKET_HOLIDAYS_2026 = set()  # type: ignore[assignment]


def _trading_days_between(start: _date_cls, end: _date_cls) -> int:
    """Count trading days strictly between `start` and `end` (both exclusive).

    Returns 0 when end <= start. Skips Sat/Sun and US market holidays. Used
    for staleness, so on Monday morning with Thursday's close as the most
    recent row this returns 1 (only Friday's bar is missing), not 4 calendar
    days. The end day is excluded because today's bar doesn't exist yet at
    market open.
    """
    if end <= start:
        return 0
    count = 0
    cur = start + timedelta(days=1)
    while cur < end:
        if cur.weekday() < 5 and cur not in MARKET_HOLIDAYS_2026:
            count += 1
        cur += timedelta(days=1)
    return count


@router.get("/api/dashboard/brief/{ticker}")
async def dashboard_brief(
    ticker: str,
    date: Optional[str] = Query(None, description="Historical date as YYYY-MM-DD. If omitted, returns latest."),
):
    """Return daily bias / strat status for the dashboard.

    Pulls from premarket_analysis and market_data_daily in Cloud SQL.
    If `date` is provided, returns the brief as of that trading day.
    If Cloud SQL is unavailable, returns source='unavailable' so the
    frontend can show an explicit alert — no silent fallbacks.
    """
    ticker = ticker.upper()

    if not _CLOUD_SQL or _query_fn is None:
        return {
            "ticker": ticker,
            "source": "unavailable",
            "reason": "Cloud SQL not connected. Check CLOUD_SQL_CONNECTION_NAME env var.",
        }

    # --- Premarket analysis (most recent, or as of date) ---
    premarket = {}
    try:
        if date:
            df = _query_fn(
                "SELECT * FROM premarket_analysis "
                "WHERE ticker = :ticker AND analysis_date <= :date "
                "ORDER BY analysis_date DESC LIMIT 1",
                {"ticker": ticker, "date": date},
            )
        else:
            df = _query_fn(
                "SELECT * FROM premarket_analysis "
                "WHERE ticker = :ticker ORDER BY analysis_date DESC LIMIT 1",
                {"ticker": ticker},
            )
        if not df.empty:
            row = df.iloc[0]
            premarket = {
                "analysis_date": str(row.get("analysis_date", "")),
                "price": float(row["price"]) if "price" in row and row["price"] is not None else None,
                "rsi": round(float(row["rsi"]), 1) if "rsi" in row and row["rsi"] is not None else None,
                "rsi_direction": row.get("rsi_direction"),
                "consecutive_up": int(row["consecutive_up"]) if "consecutive_up" in row and row["consecutive_up"] is not None else 0,
                "consecutive_down": int(row["consecutive_down"]) if "consecutive_down" in row and row["consecutive_down"] is not None else 0,
                "signal_status": row.get("signal_status"),
                "strat_candle": row.get("strat_candle"),
                "strat_combo": row.get("strat_combo"),
                "strat_setup": bool(row.get("strat_setup", False)),
                "ftfc_score": round(float(row["ftfc_score"]), 2) if "ftfc_score" in row and row["ftfc_score"] is not None else None,
                "ftfc_direction": row.get("ftfc_direction"),
            }
    except Exception as e:
        logger.warning("premarket_analysis query failed: %s", e)

    # --- Daily indicators (latest, or as of date) ---
    daily = {}
    try:
        base_cols = (
            "SELECT date, close, rsi_14, ema_9, ema_20, sma_200, "
            "       macd, bb_upper, bb_lower, atr_14, rvol, "
            "       strat_candle, strat_combo, strat_setup, "
            "       ftfc_score, ftfc_direction, "
            "       consecutive_up, consecutive_down, "
            "       price_vs_ema9, price_vs_ema20 "
            "FROM market_data_daily "
        )
        if date:
            df = _query_fn(
                base_cols + "WHERE ticker = :ticker AND date <= :date ORDER BY date DESC LIMIT 1",
                {"ticker": ticker, "date": date},
            )
        else:
            df = _query_fn(
                base_cols + "WHERE ticker = :ticker ORDER BY date DESC LIMIT 1",
                {"ticker": ticker},
            )
        if not df.empty:
            row = df.iloc[0]
            _f = lambda v, d=2: round(float(v), d) if v is not None else None
            # Detect staleness in TRADING days, not calendar days — Thursday → Monday
            # is 1 stale trading day (only Friday is missing), not 4 calendar days.
            try:
                row_date = row.get("date")
                if hasattr(row_date, "strftime"):
                    row_d = row_date
                else:
                    row_d = datetime.strptime(str(row_date), "%Y-%m-%d").date()
                ref_today = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
                stale_days = _trading_days_between(row_d, ref_today)
            except Exception:
                stale_days = 0
            daily = {
                "date": str(row.get("date", "")),
                "stale_days": stale_days,
                "close": _f(row.get("close")),
                "rsi_14": _f(row.get("rsi_14"), 1),
                "ema_9": _f(row.get("ema_9")),
                "ema_20": _f(row.get("ema_20")),
                "sma_200": _f(row.get("sma_200")),
                "macd": _f(row.get("macd"), 4),
                "atr": _f(row.get("atr_14"), 4),
                "rvol": _f(row.get("rvol")),
                "strat_candle": row.get("strat_candle"),
                "strat_combo": row.get("strat_combo"),
                "strat_setup": bool(row.get("strat_setup")) if row.get("strat_setup") is not None else None,
                "ftfc_score": _f(row.get("ftfc_score")),
                "ftfc_direction": row.get("ftfc_direction"),
                "consecutive_up": int(row["consecutive_up"]) if row.get("consecutive_up") is not None else 0,
                "consecutive_down": int(row["consecutive_down"]) if row.get("consecutive_down") is not None else 0,
                "price_vs_ema9": _f(row.get("price_vs_ema9"), 3),
                "price_vs_ema20": _f(row.get("price_vs_ema20"), 3),
            }
    except Exception as e:
        logger.warning("market_data_daily query failed: %s", e)

    # ── Live overlay ────────────────────────────────────────────────────────
    # When the market is open AND the caller is asking for "today" (no ?date=),
    # overlay live quote on top of the cached daily snapshot. Recompute RSI14,
    # EMA9, EMA20, SMA200 with a synthetic today-bar appended so the card
    # reflects the live tape instead of yesterday's close.
    live_meta: dict = {}
    if (
        daily
        and date is None
        and _is_market_open is not None
        and get_live_quote is not None
        and ET_TZ is not None
    ):
        try:
            now_et = datetime.now(ET_TZ)
            is_open, session = _is_market_open(now_et)
            if is_open:
                live_meta = await _apply_live_overlay(ticker, daily)
        except Exception as e:
            logger.warning("live overlay failed for %s: %s", ticker, e)

    # Derive bias direction from premarket first, then daily indicators
    ftfc_dir = premarket.get("ftfc_direction") or daily.get("ftfc_direction")
    if ftfc_dir in ("bullish",):
        bias = "bullish"
    elif ftfc_dir in ("bearish",):
        bias = "bearish"
    else:
        # Fall back to RSI + price vs EMA for rough bias
        rsi = premarket.get("rsi") or daily.get("rsi_14")
        pve = daily.get("price_vs_ema20")
        if rsi is not None and pve is not None:
            if rsi > 55 and pve > 0:
                bias = "bullish"
            elif rsi < 45 and pve < 0:
                bias = "bearish"
            else:
                bias = "neutral"
        else:
            bias = "neutral"

    return {
        "ticker": ticker,
        "source": "cloud_sql",
        "bias": bias,
        "has_premarket": bool(premarket),
        **premarket,
        "daily_indicators": daily,
        **({"live": live_meta} if live_meta else {}),
    }


async def _apply_live_overlay(ticker: str, daily: dict) -> dict:
    """Refresh ``daily`` in place with live-quote-driven indicators.

    Pulls the last 250 daily closes from Cloud SQL, appends a synthetic bar
    built from the live quote, and recomputes RSI14 / EMA9 / EMA20 / SMA200.
    Mutates ``daily`` and returns a small ``live`` metadata block describing
    what was overlaid (price, timestamp, source).

    Silently no-ops on any failure — caller catches and logs.
    """
    if _query_fn is None or get_live_quote is None:
        return {}

    # 1. Pull recent daily history (chronological, oldest first)
    hist = _query_fn(
        "SELECT date, close FROM market_data_daily "
        "WHERE ticker = :ticker ORDER BY date DESC LIMIT 250",
        {"ticker": ticker},
    )
    if hist.empty or len(hist) < 30:
        return {}
    hist = hist.iloc[::-1].reset_index(drop=True)

    # 2. Fetch live quote (the live router function returns a dict)
    quote = await get_live_quote(ticker)
    live_price = float(quote.get("price") or 0.0)
    if live_price <= 0:
        return {}

    # 3. Append (or replace) today's row in the close series
    import pandas as pd
    from lib.indicators import calculate_rsi, calculate_ema, calculate_sma

    today = datetime.now(ET_TZ).date() if ET_TZ else datetime.now().date()
    closes = hist["close"].astype(float).tolist()
    last_date = hist["date"].iloc[-1]
    last_d = last_date if hasattr(last_date, "year") else datetime.strptime(str(last_date), "%Y-%m-%d").date()
    if last_d == today:
        closes[-1] = live_price
    else:
        closes.append(live_price)
    series = pd.Series(closes)

    # 4. Recompute the indicators the bias card actually displays
    rsi14 = float(calculate_rsi(series, 14).iloc[-1])
    ema9 = float(calculate_ema(series, 9).iloc[-1])
    ema20 = float(calculate_ema(series, 20).iloc[-1])
    sma200 = float(calculate_sma(series, 200).iloc[-1]) if len(series) >= 200 else None

    # 5. Mutate daily so the existing field-to-UI mapping just works
    daily["close"] = round(live_price, 2)
    daily["rsi_14"] = round(rsi14, 1)
    daily["ema_9"] = round(ema9, 2)
    daily["ema_20"] = round(ema20, 2)
    if sma200 is not None:
        daily["sma_200"] = round(sma200, 2)
    daily["price_vs_ema9"] = round((live_price - ema9) / ema9 * 100.0, 3) if ema9 else None
    daily["price_vs_ema20"] = round((live_price - ema20) / ema20 * 100.0, 3) if ema20 else None
    daily["stale_days"] = 0  # live data is by definition not stale

    return {
        "price": round(live_price, 2),
        "session": quote.get("market_session", "regular"),
        "updated_at": quote.get("last_updated", ""),
        "source": "alphavantage_global_quote",
    }


# ---------------------------------------------------------------------------
# PHASE 3 — Movement Read (feature-flagged, behind-the-scenes until flipped).
#
# Surfaces the Phase 2 movement-statement assembler
# (lib.movement_statement.assemble_movement_statement) as a read-only,
# FEATURE-FLAGGED endpoint that the React "Movement Read" card renders.
#
# Architecture contract (CLAUDE.md — one source of truth):
#   The frontend RENDERS the assembler's output and recomputes nothing.
#   ALL math (headline probability, reach-rates, modifiers) lives in
#   lib/movement_statement.py. This endpoint is a thin pass-through; it
#   does NOT re-derive or alter any field.
#
# Scope guardrails (mirror the assembler's trustworthy-cell restriction):
#   - Tickers: IWM / SPY / QQQ only (validated cells).
#   - Timeframes: 5m / 15m ONLY. 30m is never consulted (calibration not
#     cleared) and is rejected with 400.
#   - Feature flag: MOVEMENT_STATEMENT_ENABLED (env var, default OFF). The
#     SAME flag the assembler reads. When OFF the endpoint returns 404 so
#     the card is genuinely absent — no UI change until the flag is ON.
#   - Rule 3.7: every UNAVAILABLE envelope produced by the assembler is
#     passed through VERBATIM. This endpoint NEVER fabricates a number, 0,
#     or 0.5 to paper over a missing piece, and never strips a reason.
# ---------------------------------------------------------------------------

MOVEMENT_STATEMENT_TICKERS = ("IWM", "SPY", "QQQ")
MOVEMENT_STATEMENT_TFS = ("5m", "15m")


def _levels_block_has_non_finite(levels) -> bool:
    """True if the levels block carries any non-finite float (NaN / inf).

    Rule 3.7 safety net: Starlette's JSON renderer rejects NaN/inf and 500s the
    whole response. The levels block is the only part of the statement that can
    carry a price-derived float (current_price, ladder prices, distances), so a
    cheap recursive scan of just that block lets the endpoint degrade levels to
    an explicit UNAVAILABLE envelope instead of crashing. Walks dict/list/tuple
    containers; any float for which math.isfinite is False trips the guard.
    """
    import math  # noqa: PLC0415

    def _walk(node) -> bool:
        if isinstance(node, float):
            return not math.isfinite(node)
        if isinstance(node, dict):
            return any(_walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(_walk(v) for v in node)
        return False

    return _walk(levels)


def _movement_statement_enabled() -> bool:
    """Feature flag — default OFF.

    Read at request time (not import time) so the flag can be flipped via
    env var / Cloud Run config without a code change. Accepts the common
    truthy spellings; everything else (including unset) is OFF. Mirrors
    lib.movement_statement.is_enabled() exactly.
    """
    raw = os.environ.get("MOVEMENT_STATEMENT_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _build_movement_level_map(ticker: str):
    """Best-effort LevelMap for the movement statement, or None.

    The assembler degrades the levels block to an explicit UNAVAILABLE
    envelope when level_map is None (Rule 3.7 — never a fabricated ladder),
    so this helper is allowed to return None on any data gap. It builds the
    SAME LevelMap the premarket brief builds (lib.strat_levels.build_level_map
    over the daily bars + computed historical levels) so the levels-to-go
    ladder matches the rest of the platform — no duplicated math.

    Returns None (→ levels UNAVAILABLE) rather than raising, because a
    missing LevelMap is a legitimate "data unavailable" state for ONE block
    of the statement, not a reason to fail the whole read.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        from lib.data_loader import DataLoader  # noqa: PLC0415
        from lib.indicators import calculate_historical_levels  # noqa: PLC0415
        from lib.strat_levels import build_level_map  # noqa: PLC0415

        loader = DataLoader()
        df = loader.load_daily(ticker, on_stale="warn")
        if df is None or df.empty or len(df) < 2:
            return None
        close_col = "Close" if "Close" in df.columns else "Last"
        if close_col not in df.columns:
            return None
        # Rule 3.7 — never anchor levels to a NaN/NULL close. market_data_daily
        # can carry a same-day PREMARKET PLACEHOLDER row (close NULL/NaN) that
        # DataLoader.load_daily keeps; float(NaN) does NOT raise, so an
        # unfiltered df[close_col].iloc[-1] would push NaN into build_level_map →
        # level_map.current_price = NaN → Starlette rejects NaN at JSON render →
        # 500 on an otherwise-valid request. Filter to rows whose OHLC quad is
        # fully real (non-null, non-NaN) and anchor to the LAST VALID close. If no
        # valid close row remains, return None → the assembler degrades the levels
        # block to an explicit UNAVAILABLE envelope (never a fabricated ladder).
        ohlc_cols = [c for c in ("Open", "High", "Low", close_col) if c in df.columns]
        df = df[df[ohlc_cols].notna().all(axis=1)]
        if df.empty or len(df) < 2:
            return None
        ts = df["Time"] if "Time" in df.columns else pd.Series(df.index)
        levels_df = calculate_historical_levels(
            ts, df["High"], df["Low"], df["Open"], df[close_col],
        )
        for col in levels_df.columns:
            df[col] = levels_df[col].values
        current_price = float(df[close_col].iloc[-1])
        # Defensive second guard: if the last valid close is somehow still not a
        # finite number, refuse to build levels rather than ship NaN downstream.
        if not pd.notna(current_price):
            return None
        atr_col = "atr_14" if "atr_14" in df.columns else None
        atr_for_filter = None
        if atr_col is not None and pd.notna(df[atr_col].iloc[-1]):
            atr_for_filter = float(df[atr_col].iloc[-1]) or None
        return build_level_map(
            ticker=ticker,
            daily_df=df,
            current_price=current_price,
            atr=atr_for_filter,
        )
    except Exception as exc:  # data gap → None → levels UNAVAILABLE (Rule 3.7)
        logger.warning("movement-statement level map unavailable for %s: %s", ticker, exc)
        return None


@router.get("/api/movement-statement")
async def movement_statement(
    ticker: str = Query(..., description="One of IWM / SPY / QQQ (validated cells)."),
    timeframe: str = Query("15m", description="5m or 15m ONLY (30m is never consulted)."),
):
    """PHASE 3 — read-only, feature-flagged movement statement.

    Calls lib.movement_statement.assemble_movement_statement and returns its
    dict verbatim (UNAVAILABLE envelopes included). The React "Movement Read"
    card renders this output and recomputes nothing.

    Behaviour:
      - Flag OFF (default): 404 — the card is genuinely absent, no UI change.
      - Flag ON, invalid ticker/timeframe: 400.
      - Flag ON, valid cell: 200 with the assembled statement (which itself
        carries per-field OK / UNAVAILABLE status — passed through unfabricated).
    """
    # Feature flag — when OFF the endpoint behaves as if it doesn't exist so
    # the card simply does not render (no user-visible change while OFF).
    if not _movement_statement_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    ticker_u = (ticker or "").upper().strip()
    tf = (timeframe or "").strip()
    if ticker_u not in MOVEMENT_STATEMENT_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ticker must be one of {MOVEMENT_STATEMENT_TICKERS} "
                f"(validated cells); got {ticker_u!r}"
            ),
        )
    if tf not in MOVEMENT_STATEMENT_TFS:
        # 30m (and anything else) is intentionally rejected — not cleared.
        raise HTTPException(
            status_code=400,
            detail=(
                f"timeframe must be one of {MOVEMENT_STATEMENT_TFS}; got {tf!r} "
                "(30m is never consulted — calibration not cleared)"
            ),
        )

    from lib.movement_statement import assemble_movement_statement  # noqa: PLC0415

    level_map = _build_movement_level_map(ticker_u)
    result = assemble_movement_statement(ticker_u, tf, level_map=level_map)

    # Defensive: the assembler returns None only when the flag is OFF, but we
    # already gated on the flag above. If it still returns None (e.g. an env
    # race), surface 404 rather than a null body — never fabricate a payload.
    if result is None:
        raise HTTPException(status_code=404, detail="Not Found")

    # Final NaN guard (Rule 3.7): _build_movement_level_map already refuses to
    # anchor levels to a NaN close, but belt-and-suspenders — if ANY non-finite
    # float (NaN/inf) ever reaches the levels block, Starlette would reject it
    # during JSON rendering and 500 an otherwise-valid request. Degrade the
    # levels block to an explicit UNAVAILABLE envelope instead of crashing.
    if _levels_block_has_non_finite(result.get("levels")):
        logger.warning(
            "movement-statement levels for %s carried a non-finite value; "
            "degrading levels to UNAVAILABLE rather than emitting NaN",
            ticker_u,
        )
        result["levels"] = {
            "status": "UNAVAILABLE",
            "reason": "no valid daily close to anchor levels",
        }
    return result
