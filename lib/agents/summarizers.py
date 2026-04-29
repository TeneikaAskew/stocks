"""
Deterministic SQL summarizers for the agent pipeline.

These are pure Python functions that query existing Cloud SQL tables
(or on-disk parquets where a table doesn't exist yet) and return
typed dicts. No LLM calls. They exist so every agent prompt is
grounded in real platform state — the LLMs reason *over* this JSON,
they don't fetch it.

One function per analyst section plus a catalyst lookup and a
journal-memory retrieval. Each returns a dict that's trivially
JSON-serializable for embedding in a prompt.

All DB access goes through `gcp.database.query_to_dataframe`, which
returns an empty DataFrame on failure — summarizers degrade to
`{'available': False, 'reason': ...}` rather than raising. The
orchestrator passes degraded bundles to analysts with a clear flag
so the final report can mark which sections were missing.
"""

from __future__ import annotations

import logging
import math
from datetime import date as date_type, datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from .embeddings import format_vector_literal
from .schema import JournalRef

logger = logging.getLogger(__name__)


def _query(sql: str, params: Optional[dict] = None):
    """Lazy wrapper — defer gcp.database import so unit tests can
    monkey-patch a fake query fn without requiring sqlalchemy."""
    from gcp.database import query_to_dataframe

    return query_to_dataframe(sql, params or {})


def _scalar(row, col, cast=float, digits: Optional[int] = None):
    """Null-safe scalar extraction from a pandas Series row."""
    val = row.get(col)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        out = cast(val)
    except (TypeError, ValueError):
        return None
    if digits is not None and isinstance(out, float):
        return round(out, digits)
    return out


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


# ---------------------------------------------------------------------------
# 1. Market context
# ---------------------------------------------------------------------------


def summarize_market_context(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Daily OHLCV + indicators + regime classification.

    Reads market_data_daily for the row at or before `as_of` (default:
    latest). Computes a regime tag (trending up/down/ranging) and a
    20-day realized vol tag (low/normal/elevated).
    """
    sql = (
        "SELECT date, open, high, low, close, volume, "
        "       sma_200, ema_20, ema_50, rsi_14, macd, macd_signal, "
        "       macd_histogram, bb_upper, bb_lower, bb_pct, atr_14, "
        "       rvol, volatility_20d, price_vs_ema20, "
        "       pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr "
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        + ("AND date <= :as_of " if as_of else "")
        + "ORDER BY date DESC LIMIT 1"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no market_data_daily row for {ticker}")

    row = df.iloc[0]
    close = _scalar(row, "close", digits=2)
    ema_20 = _scalar(row, "ema_20", digits=2)
    sma_200 = _scalar(row, "sma_200", digits=2)
    rsi = _scalar(row, "rsi_14", digits=1)
    vol20 = _scalar(row, "volatility_20d", digits=3)
    price_vs_ema20 = _scalar(row, "price_vs_ema20", digits=3)

    # Trend tag
    above_200 = None
    if close is not None and sma_200 is not None:
        above_200 = close > sma_200
    if above_200 is True and (price_vs_ema20 or 0) > 0:
        regime = "trending_up"
    elif above_200 is False and (price_vs_ema20 or 0) < 0:
        regime = "trending_down"
    else:
        regime = "ranging"

    # Vol tag (annualized 20d realized)
    if vol20 is None:
        vol_tag = "unknown"
    elif vol20 < 0.12:
        vol_tag = "low"
    elif vol20 < 0.22:
        vol_tag = "normal"
    else:
        vol_tag = "elevated"

    # Pre-market context block (4 AM - 9:30 AM ET, populated by the
    # 11 PM ET fetcher on the prior trading day OR by today's morning
    # backfill). Surfaces to the LLM analyst so entry zones can
    # reference today's pre-market range, not just yesterday's H/L —
    # the 4/27 brief failed precisely because it didn't have this.
    pre_high = _scalar(row, "pre_high", digits=2)
    pre_low = _scalar(row, "pre_low", digits=2)
    gap_pct = _scalar(row, "gap_pct", digits=3)
    pre_range_atr = _scalar(row, "pre_range_atr", digits=3)
    pre_volume_raw = row.get("pre_volume")
    try:
        pre_volume = int(pre_volume_raw) if pre_volume_raw is not None else None
    except (TypeError, ValueError):
        pre_volume = None
    premarket_block = None
    if pre_high is not None or pre_low is not None or gap_pct is not None:
        # Tag gap regime so the LLM analyst doesn't have to interpret raw %
        gap_tag = None
        if gap_pct is not None:
            ag = abs(gap_pct)
            if ag < 0.2:
                gap_tag = "flat"
            elif ag < 0.5:
                gap_tag = "small"
            elif ag < 1.0:
                gap_tag = "moderate"
            else:
                gap_tag = "large"
        # Tag pre-market range expansion: > 0.5 ATR is regime-shifting
        range_tag = None
        if pre_range_atr is not None:
            range_tag = (
                "wide" if pre_range_atr > 0.5
                else "normal" if pre_range_atr > 0.2
                else "tight"
            )
        premarket_block = {
            "pre_high": pre_high,
            "pre_low": pre_low,
            "pre_vwap": _scalar(row, "pre_vwap", digits=2),
            "pre_volume": pre_volume,
            "gap_pct": gap_pct,
            "gap_tag": gap_tag,
            "pre_range_atr": pre_range_atr,
            "range_tag": range_tag,
        }

    return {
        "available": True,
        "date": str(row.get("date", "")),
        "close": close,
        "ema_20": ema_20,
        "sma_200": sma_200,
        "above_sma_200": above_200,
        "rsi_14": rsi,
        "price_vs_ema20_pct": price_vs_ema20,
        "bb_pct": _scalar(row, "bb_pct", digits=3),
        "atr_14": _scalar(row, "atr_14", digits=2),
        "rvol": _scalar(row, "rvol", digits=2),
        "volatility_20d": vol20,
        "regime": regime,
        "vol_tag": vol_tag,
        "macd": _scalar(row, "macd", digits=4),
        "macd_histogram": _scalar(row, "macd_histogram", digits=4),
        # Pre-market context — None when not yet computed (e.g. weekend,
        # or fetcher hasn't run for this date). The LLM prompt should
        # weight pre_high/pre_low over prev_day_high/low whenever
        # gap_tag != 'flat'.
        "premarket": premarket_block,
    }


# ---------------------------------------------------------------------------
# 2. Strat status (live recompute from market_data_daily — audit fix #10)
# ---------------------------------------------------------------------------


def summarize_strat_status(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Rob Smith strat state — delegates to lib.strat.compute_strat_status.

    Single source of truth: the same helper the 8:30 AM premarket-brief
    uses, so the LLM analyst sees the *exact* candle / combo / FTFC
    triplet that gets posted to Discord. No more reading stale NULL
    columns from market_data_daily.

    Also surfaces the multi-timeframe level map (PDH/PDL/PWH/PWL/PMH/PML/
    PQH/PQL/PYH/PYL) and the mother-bar walk-back ``effective_pdh`` /
    ``effective_pdl`` for inside-of-inside compressions. The deterministic
    trade planner uses these to walk the level hierarchy on gap days
    instead of always anchoring entry at PDH/PDL.
    """
    from lib.strat import compute_strat_status

    status = compute_strat_status(ticker, as_of=as_of)
    if not status.get("available"):
        return _unavailable(status.get("reason") or f"strat unavailable for {ticker}")

    # StratSnapshot in schema.py rounds scores to 2 dp.
    score = status.get("ftfc_score")
    if score is not None:
        score = round(float(score), 2)
    th = status.get("trigger_high")
    tl = status.get("trigger_low")

    out = {
        "available": True,
        "date": status.get("date", ""),
        "last_candle": status.get("last_candle") or "1",
        "in_force_combo": status.get("in_force_combo"),
        "strat_setup": bool(status.get("strat_setup", False)),
        "ftfc_score": score if score is not None else 0.0,
        "ftfc_direction": status.get("ftfc_direction") or "mixed",
        "trigger_high": round(float(th), 2) if th is not None else None,
        "trigger_low": round(float(tl), 2) if tl is not None else None,
    }

    # Multi-timeframe level map. Built from the same daily history
    # `compute_strat_status` already trimmed to the as_of cutoff (so
    # historical replays don't see future bars). Computed best-effort —
    # if the level builder errors on this ticker the strat dict still
    # returns; the planner falls back to single-level PDH/PDL behaviour.
    try:
        from lib.data_loader import DataLoader
        from lib.strat_levels import compute_previous_levels
        loader = DataLoader()
        df = loader.load_daily(ticker)
        if df is not None and not df.empty:
            # Apply the same as_of cutoff lib.strat.compute_strat_status
            # uses, with the same tz normalization to avoid the leak
            # patched in PR #135.
            if as_of is not None:
                import pandas as _pd
                cutoff = _pd.Timestamp(as_of)
                if cutoff.tz is not None:
                    cutoff = cutoff.tz_convert('UTC').tz_localize(None)
                if isinstance(df.index, _pd.DatetimeIndex) and df.index.tz is not None:
                    df = df.copy()
                    df.index = df.index.tz_localize(None)
                df = df[df.index <= cutoff]
            level_map = compute_previous_levels(df)
            level_dict: dict[str, float] = {}
            for name in ("PDH", "PDL", "PWH", "PWL", "PMH", "PML",
                         "PQH", "PQL", "PYH", "PYL"):
                lv = level_map.get(name)
                if lv is not None:
                    level_dict[name] = round(float(lv.price), 2)

            # Mother-bar walk-back for inside-of-inside compressions.
            # When the prior bar is a strat '1' (inside bar), price has
            # been compressing within an outer "mother bar" — the real
            # PDH/PDL trigger is the OUTER mother bar's H/L, not the
            # inside bar's. Walk back through consecutive '1' bars to
            # find the bar that contained them.
            try:
                from lib.strat import StratClassifier
                clf = StratClassifier()
                ohlc = df[['Open', 'High', 'Low', 'Close']]
                labels = clf.classify_series(ohlc)
                eff_pdh, eff_pdl = _walk_back_to_mother_bar(df, labels)
                if eff_pdh is not None:
                    level_dict["effective_PDH"] = round(float(eff_pdh), 2)
                if eff_pdl is not None:
                    level_dict["effective_PDL"] = round(float(eff_pdl), 2)
            except Exception:
                # Walk-back failed — planner will fall back to PDH/PDL
                pass

            if level_dict:
                out["levels"] = level_dict
    except Exception:
        # Level map best-effort — never block the strat block from returning
        pass

    return out


def _walk_back_to_mother_bar(df, labels) -> tuple[Optional[float], Optional[float]]:
    """Walk back through consecutive inside bars to find the mother bar.

    Returns the H/L of the most recent bar BEFORE today whose range
    contains every subsequent inside bar up through yesterday. Falls
    back to yesterday's H/L when yesterday was a directional bar
    (2U/2D/3) rather than a '1'.

    Used by ``summarize_strat_status`` to populate ``effective_PDH`` /
    ``effective_PDL`` so the trade planner uses the structural trigger
    (the outer mother bar) on inside-of-inside compressions instead of
    yesterday's tighter inside-bar range.
    """
    if len(df) < 2 or len(labels) < 2:
        return None, None
    # iloc[-1] is "today" (the as_of cutoff bar) — we don't trigger on
    # it. iloc[-2] is yesterday — the canonical PDH source. Walk back
    # only when yesterday is a '1' (inside) bar.
    i = -2
    if str(labels.iloc[i]) != '1':
        try:
            return float(df.iloc[i]['High']), float(df.iloc[i]['Low'])
        except (KeyError, ValueError, TypeError):
            return None, None
    # Walk further back through consecutive '1' bars
    LOOKBACK = 10  # cap so we don't walk to the start of history
    while i - 1 >= -min(LOOKBACK, len(df)) and str(labels.iloc[i - 1]) == '1':
        i -= 1
    # Mother bar = the bar BEFORE the inside-bar chain started
    mother_idx = i - 1
    if mother_idx < -len(df):
        return None, None
    try:
        return float(df.iloc[mother_idx]['High']), float(df.iloc[mother_idx]['Low'])
    except (KeyError, ValueError, TypeError):
        return None, None


# ---------------------------------------------------------------------------
# 3. Options flow
# ---------------------------------------------------------------------------


def summarize_options_flow(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Latest AlphaVantage EOD options chain snapshot aggregates.

    Returns total call/put volume, put/call ratio, max-pain strike,
    top open-interest strikes, and weighted average IV.
    """
    sql = (
        "SELECT option_type, strike, volume, open_interest, "
        "       implied_volatility, delta "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        + ("AND snapshot_date <= :as_of " if as_of else "")
        + "  AND snapshot_date = ("
        "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker AND data_source = 'alphavantage'"
        + ("      AND snapshot_date <= :as_of" if as_of else "")
        + "  )"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no etf_options_snapshots for {ticker}")

    calls = df[df["option_type"] == "calls"]
    puts = df[df["option_type"] == "puts"]
    call_vol = int(calls["volume"].fillna(0).sum())
    put_vol = int(puts["volume"].fillna(0).sum())
    pcr = round(put_vol / call_vol, 3) if call_vol > 0 else None

    # Max pain: strike that minimizes total dollar payout of ITM options
    # Approximation: the strike where call OI + put OI is maximized (simple proxy)
    if not df.empty:
        oi_by_strike = (
            df.groupby("strike")["open_interest"].sum().fillna(0).sort_values(ascending=False)
        )
        top_strikes = oi_by_strike.head(5).index.tolist()
        max_pain_proxy = float(oi_by_strike.idxmax()) if not oi_by_strike.empty else None
    else:
        top_strikes = []
        max_pain_proxy = None

    # Weighted-average IV by volume
    vol_series = df["volume"].fillna(0)
    iv_series = df["implied_volatility"].fillna(0)
    total_vol = vol_series.sum()
    avg_iv = (
        round(float((iv_series * vol_series).sum() / total_vol), 3)
        if total_vol > 0
        else None
    )

    return {
        "available": True,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "put_call_ratio": pcr,
        "max_pain_strike_proxy": max_pain_proxy,
        "top_oi_strikes": [float(s) for s in top_strikes],
        "vol_weighted_iv": avg_iv,
        "contract_count": int(len(df)),
    }


# ---------------------------------------------------------------------------
# 3b. Gamma levels (King / Gate / Spot / Flip taxonomy + regime)
# ---------------------------------------------------------------------------


def summarize_gamma_levels(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Stratalyst-style gamma analytics: King / Gate / Spot / Flip + regime.

    Pulls the latest AlphaVantage chain for the ticker (or the most recent
    snapshot on or before `as_of`) and runs lib.gamma.build_summary. The
    output feeds the gamma analyst prompt; any consumer wanting a richer
    response should call the /api/options/{ticker}/{date}/levels endpoint
    directly instead of consuming this summary.
    """
    from lib import gamma  # local import to avoid circular at module load

    sql = (
        "SELECT option_type, strike, expiration, "
        "       open_interest, gamma, vega, delta, "
        "       bid, ask, mark, last_price "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        + ("AND snapshot_date <= :as_of " if as_of else "")
        + "  AND snapshot_date = ("
        "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker AND data_source = 'alphavantage'"
        + ("      AND snapshot_date <= :as_of" if as_of else "")
        + "  )"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no etf_options_snapshots for {ticker}")

    # Map the chain rows to the dict shape lib.gamma accepts.
    type_map = {"calls": "call", "puts": "put"}
    options = []
    for row in df.to_dict(orient="records"):
        exp = row.get("expiration")
        if hasattr(exp, "strftime"):
            exp = exp.strftime("%Y-%m-%d")
        options.append({
            "type": type_map.get(row.get("option_type"), row.get("option_type")),
            "strike": row.get("strike"),
            "expiration": exp,
            "open_interest": row.get("open_interest"),
            "gamma": row.get("gamma"),
            "vega": row.get("vega"),
            "delta": row.get("delta"),
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "mark": row.get("mark"),
            "last": row.get("last_price"),
        })

    snapshot_date = str(as_of) if as_of else "latest"
    summary = gamma.build_summary(
        ticker=ticker,
        snapshot_date=snapshot_date,
        options=options,
    )

    # Compact shape for the analyst — full GammaSummary is too verbose.
    def _level_brief(lv: gamma.Level) -> dict:
        return {
            "strike": lv.strike,
            "gex": round(lv.gex, 0),
            "distance_pct": round(lv.distance_pct, 2),
            "call_oi": lv.call_oi,
            "put_oi": lv.put_oi,
        }

    return {
        "available": True,
        "spot": round(summary.spot.price, 2),
        "spot_method": summary.spot.method,
        "flip": round(summary.flip, 2) if summary.flip else None,
        "regime": summary.regime,
        "total_gex": round(summary.total_gex, 0),
        "kings": [_level_brief(lv) for lv in summary.kings[:3]],
        "gates": [_level_brief(lv) for lv in summary.gates[:5]],
        "flip_levels": [_level_brief(lv) for lv in summary.flip_levels],
        "warnings": summary.warnings,
        "chain_size": len(options),
    }


# ---------------------------------------------------------------------------
# 4. Signal history
# ---------------------------------------------------------------------------


def summarize_signals_history(
    ticker: str,
    lookback_days: int = 30,
    as_of: Optional[date_type] = None,
) -> dict:
    """signal_alerts aggregates anchored at `as_of`.

    Returns the `lookback_days` window ending at `as_of` (defaults to
    now when None). Grouped by direction/strength, with the 5 most
    recent rows for reference. Historical runs therefore see the same
    data the live platform would have seen on `as_of`, not today's
    live signals.
    """
    if as_of is None:
        sql = (
            "SELECT alert_ts, direction, strength_label, total_score "
            "FROM signal_alerts "
            "WHERE ticker = :ticker "
            "  AND alert_ts >= NOW() - (:days || ' days')::interval "
            "ORDER BY alert_ts DESC"
        )
        params: dict[str, Any] = {"ticker": ticker.upper(), "days": lookback_days}
    else:
        # CAST() rather than ::timestamptz because SQLAlchemy text()
        # collides with the `::` cast syntax when it appears right
        # after a :param reference. Explicit cast also fixes pg8000
        # TEXT binding for `end - interval` math.
        # Use start of the *next* day with `<` so that all intraday
        # alerts on `as_of` are included (str(date) resolves to midnight
        # at the *start*, which would exclude the entire day with `<=`).
        end_exclusive = as_of + timedelta(days=1)
        sql = (
            "SELECT alert_ts, direction, strength_label, total_score "
            "FROM signal_alerts "
            "WHERE ticker = :ticker "
            "  AND alert_ts < CAST(:end_ts AS timestamptz) "
            "  AND alert_ts >= CAST(:end_ts AS timestamptz) - (:days || ' days')::interval "
            "ORDER BY alert_ts DESC"
        )
        params = {
            "ticker": ticker.upper(),
            "days": lookback_days,
            "end_ts": str(end_exclusive),
        }
    df = _query(sql, params)
    if df.empty:
        return {
            "available": True,
            "lookback_days": lookback_days,
            "total_alerts": 0,
            "call_count": 0,
            "put_count": 0,
            "recent": [],
        }

    call_count = int((df["direction"] == "CALL").sum())
    put_count = int((df["direction"] == "PUT").sum())
    recent_rows = df.head(5).to_dict(orient="records")
    recent = [
        {
            "alert_ts": str(r["alert_ts"]),
            "direction": r["direction"],
            "strength": r.get("strength_label") or "unknown",
            "score": float(r["total_score"]) if r.get("total_score") is not None else 0.0,
        }
        for r in recent_rows
    ]

    return {
        "available": True,
        "lookback_days": lookback_days,
        "total_alerts": int(len(df)),
        "call_count": call_count,
        "put_count": put_count,
        "recent": recent,
    }


# ---------------------------------------------------------------------------
# 5. Backtest metrics
# ---------------------------------------------------------------------------


def summarize_backtest_metrics(
    ticker: str,
    lookback_days: int = 90,
    as_of: Optional[date_type] = None,
    *,
    cross_ticker: bool = True,
) -> dict:
    """Catalyst-analog 'backtest' for the ticker's current pattern.

    Walk-forward backtests of a single discretionary trade aren't
    meaningful (one trade). Instead, this function answers the
    question a Wall-Street analyst would ask: *given the price
    pattern visible today (gap, volume, RSI, regime), find prior
    days where the same pattern appeared and report what happened
    over the next 1, 3, 5, 10 trading days*.

    `cross_ticker=True` (default) extends the analog universe to
    every other ticker in `market_data_daily`. Same-ticker matches
    are tried first; cross-ticker is appended only if fewer than
    10 same-ticker matches exist (or if same-ticker is empty). Each
    analog row carries the source ticker so the user can see
    whether the historical move came from AVGO itself or e.g. SPY.

    No `trades` table dependency. Runs entirely against
    `market_data_daily` (which we already backfill).

    Output (when available=True):
        pattern_today: dict — features describing today's setup
        analog_count: int   — how many historical matches
        cross_ticker_used: bool — whether cross-ticker analogs were merged
        forward_returns: dict — day_1/3/5/10 stats (median, mean,
                                win_rate, p25, p75, max, min)
        top_analogs: list[dict] — up to 5 closest historical
                                   examples with their forward moves
    """
    cutoff = as_of or datetime.now(timezone.utc).date()

    # 1. Pull raw OHLCV history. We compute indicators inline below
    #    rather than reading rsi_14 / sma_200 / ema_20 from the table —
    #    those columns are only populated for the most recent bar by
    #    compute_and_upsert_daily_indicators(), so a bulk-backfilled
    #    ticker (e.g. AVGO via outputsize=full) has NULLs everywhere
    #    else and analog matching would silently return nothing.
    df = _query(
        "SELECT date, open, high, low, close, volume "
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        "  AND date <= CAST(:cutoff AS date) "
        "ORDER BY date ASC",
        {"ticker": ticker.upper(), "cutoff": str(cutoff)},
    )
    if df is None or len(df) < 60:
        return _unavailable(
            f"only {0 if df is None else len(df)} daily bars for {ticker} — "
            "need >= 60 to compute analog backtest"
        )

    # 2. Compute indicators + match features.
    df = df.reset_index(drop=True)
    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)

    # RSI(14) — Wilder
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))
    # SMA200 + EMA20
    df["sma_200"] = df["close"].rolling(200).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()

    df["prev_close"] = df["close"].shift(1)
    df["gap_pct"] = (df["open"] - df["prev_close"]) / df["prev_close"] * 100
    df["range_pct"] = (df["high"] - df["low"]) / df["prev_close"] * 100
    df["close_pct"] = (df["close"] - df["prev_close"]) / df["prev_close"] * 100
    df["vol_20d_avg"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_20d_avg"]
    df["close_vs_sma200_pct"] = (df["close"] - df["sma_200"]) / df["sma_200"] * 100
    df["close_vs_ema20_pct"] = (df["close"] - df["ema_20"]) / df["ema_20"] * 100

    # 3. Forward returns for every historical row (close-to-close).
    for n in (1, 3, 5, 10):
        df[f"fwd_{n}d"] = (df["close"].shift(-n) - df["close"]) / df["close"] * 100

    # 4. Today's pattern.
    today = df.iloc[-1]
    if any(pd.isna(today[c]) for c in
           ["gap_pct", "vol_ratio", "rsi_14", "close_vs_sma200_pct"]):
        return _unavailable("today's row has missing indicator features")

    pattern = {
        "date": str(today["date"]),
        "gap_pct": round(float(today["gap_pct"]), 2),
        "vol_ratio": round(float(today["vol_ratio"]), 2),
        "close_pct": round(float(today["close_pct"]), 2),
        "rsi_14": round(float(today["rsi_14"]), 1),
        "close_vs_sma200_pct": round(float(today["close_vs_sma200_pct"]), 2),
        "close_vs_ema20_pct": round(float(today["close_vs_ema20_pct"]), 2),
    }

    # 5. Match historical rows. Drop the current row + any rows in last
    #    20d to avoid trivial overlap. Match each feature within a
    #    tolerance band; widen progressively if matches are sparse.
    df["ticker"] = ticker.upper()
    history = df.iloc[:-20].dropna(subset=[
        "gap_pct", "vol_ratio", "rsi_14", "close_vs_sma200_pct",
        "fwd_1d", "fwd_5d",
    ])
    if history.empty:
        return _unavailable("not enough complete history for analog match")

    def _matches_in(frame, tol_gap, tol_vol, tol_rsi, tol_sma):
        return frame[
            (frame["gap_pct"].between(pattern["gap_pct"] - tol_gap,
                                      pattern["gap_pct"] + tol_gap))
            & (frame["vol_ratio"].between(pattern["vol_ratio"] - tol_vol,
                                          pattern["vol_ratio"] + tol_vol))
            & (frame["rsi_14"].between(pattern["rsi_14"] - tol_rsi,
                                       pattern["rsi_14"] + tol_rsi))
            & (frame["close_vs_sma200_pct"].between(
                pattern["close_vs_sma200_pct"] - tol_sma,
                pattern["close_vs_sma200_pct"] + tol_sma,
            ))
        ]

    # Tolerance bands progressively widen until we have ≥5 matches.
    bands = [
        (1.0, 0.5, 5.0, 5.0),    # tight
        (2.0, 1.0, 8.0, 10.0),   # medium
        (3.0, 1.5, 12.0, 15.0),  # loose
        (5.0, 2.0, 20.0, 25.0),  # very loose
    ]
    matched = pd.DataFrame()
    band_used = None
    for band in bands:
        matched = _matches_in(history, *band)
        if len(matched) >= 5:
            band_used = band
            break

    cross_used = False
    # If same-ticker matches are sparse, expand to every other ticker
    # in the table at the *same* tolerance band — keeps match quality
    # comparable while widening the analog universe.
    if cross_ticker and len(matched) < 10:
        cross_history = _build_cross_ticker_history(ticker, str(cutoff))
        if cross_history is not None and not cross_history.empty:
            target_band = band_used or bands[-1]
            cross_matched = _matches_in(cross_history, *target_band)
            if not cross_matched.empty:
                matched = pd.concat([matched, cross_matched], ignore_index=True)
                cross_used = True

    if len(matched) < 3:
        return {
            "available": True,
            "pattern_today": pattern,
            "analog_count": int(len(matched)),
            "tolerance_bands_used": band_used or bands[-1],
            "cross_ticker_used": cross_used,
            "forward_returns": None,
            "top_analogs": [],
            "note": (
                f"only {len(matched)} historical analog(s) — too few for "
                "stable forward-return statistics"
            ),
        }

    def stats(col: str) -> dict:
        s = matched[col].dropna()
        if s.empty:
            return {"n": 0}
        return {
            "n": int(len(s)),
            "median_pct": round(float(s.median()), 2),
            "mean_pct": round(float(s.mean()), 2),
            "p25_pct": round(float(s.quantile(0.25)), 2),
            "p75_pct": round(float(s.quantile(0.75)), 2),
            "max_pct": round(float(s.max()), 2),
            "min_pct": round(float(s.min()), 2),
            "win_rate": round(float((s > 0).mean()), 3),
        }

    forward = {f"day_{n}": stats(f"fwd_{n}d") for n in (1, 3, 5, 10)}

    # 6. Top 5 closest analogs by Euclidean distance over normalized features.
    feat_cols = ["gap_pct", "vol_ratio", "rsi_14", "close_vs_sma200_pct"]
    pattern_vec = np.array([pattern[c] for c in feat_cols], dtype=float)
    feat_arr = matched[feat_cols].to_numpy(dtype=float)
    # normalize each feature by its std across the match set so no
    # single feature dominates distance
    std = feat_arr.std(axis=0)
    std[std == 0] = 1.0
    diffs = (feat_arr - pattern_vec) / std
    matched = matched.assign(_dist=np.linalg.norm(diffs, axis=1))
    closest = matched.nsmallest(5, "_dist")

    top = [
        {
            "ticker": str(r.get("ticker", ticker.upper())),
            "date": str(r["date"]),
            "gap_pct": round(float(r["gap_pct"]), 2),
            "vol_ratio": round(float(r["vol_ratio"]), 2),
            "rsi_14": round(float(r["rsi_14"]), 1),
            "close": round(float(r["close"]), 2),
            "fwd_1d": _round_or_none(r.get("fwd_1d")),
            "fwd_3d": _round_or_none(r.get("fwd_3d")),
            "fwd_5d": _round_or_none(r.get("fwd_5d")),
            "fwd_10d": _round_or_none(r.get("fwd_10d")),
        }
        for _, r in closest.iterrows()
    ]

    return {
        "available": True,
        "pattern_today": pattern,
        "analog_count": int(len(matched)),
        "tolerance_bands_used": band_used,
        "cross_ticker_used": cross_used,
        "forward_returns": forward,
        "top_analogs": top,
    }


def _round_or_none(v):
    if v is None or pd.isna(v):
        return None
    return round(float(v), 2)


def _build_cross_ticker_history(target_ticker: str, cutoff: str):
    """Pull every other ticker's daily history and engineer the same
    feature set used for analog matching. Returned frame has a `ticker`
    column so each match can be attributed to its source.

    Implementation: a single SQL pull (orders ticker, date so groupby
    is contiguous), then a per-ticker pandas pipeline. This is fine for
    the current ~5-ticker analog universe — if we ever need to scale
    past 50 tickers, push the gap/vol/RSI math into SQL window
    functions instead.
    """
    df = _query(
        "SELECT ticker, date, open, high, low, close, volume "
        "FROM market_data_daily "
        "WHERE ticker <> :ticker "
        "  AND date <= CAST(:cutoff AS date) "
        "ORDER BY ticker ASC, date ASC",
        {"ticker": target_ticker.upper(), "cutoff": cutoff},
    )
    if df is None or df.empty:
        return None

    out_frames: list[pd.DataFrame] = []
    for tk, group in df.groupby("ticker", sort=False):
        if len(group) < 60:
            continue
        g = group.reset_index(drop=True).copy()
        g["close"] = g["close"].astype(float)
        g["open"] = g["open"].astype(float)
        g["high"] = g["high"].astype(float)
        g["low"] = g["low"].astype(float)
        g["volume"] = g["volume"].astype(float)

        delta = g["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        g["rsi_14"] = 100 - (100 / (1 + rs))
        g["sma_200"] = g["close"].rolling(200).mean()
        g["ema_20"] = g["close"].ewm(span=20, adjust=False).mean()

        g["prev_close"] = g["close"].shift(1)
        g["gap_pct"] = (g["open"] - g["prev_close"]) / g["prev_close"] * 100
        g["range_pct"] = (g["high"] - g["low"]) / g["prev_close"] * 100
        g["close_pct"] = (g["close"] - g["prev_close"]) / g["prev_close"] * 100
        g["vol_20d_avg"] = g["volume"].rolling(20).mean()
        g["vol_ratio"] = g["volume"] / g["vol_20d_avg"]
        g["close_vs_sma200_pct"] = (g["close"] - g["sma_200"]) / g["sma_200"] * 100
        g["close_vs_ema20_pct"] = (g["close"] - g["ema_20"]) / g["ema_20"] * 100
        for n in (1, 3, 5, 10):
            g[f"fwd_{n}d"] = (g["close"].shift(-n) - g["close"]) / g["close"] * 100

        # Drop the most recent 20 days so the analog window mirrors
        # the same-ticker logic and we don't include trivially-recent
        # patterns from peer tickers either.
        g = g.iloc[:-20].dropna(subset=[
            "gap_pct", "vol_ratio", "rsi_14",
            "close_vs_sma200_pct", "fwd_1d", "fwd_5d",
        ])
        if not g.empty:
            out_frames.append(g)

    if not out_frames:
        return None
    return pd.concat(out_frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 6. Catalysts (economic + earnings)
# ---------------------------------------------------------------------------


def summarize_catalysts(
    ticker: str, as_of: Optional[date_type] = None,
    lookahead_days: int = 14, news_lookback_days: int = 3,
    sec_lookback_days: int = 5,
) -> dict:
    """Catalysts surrounding the as_of date.

    Combines four sources:
      * `economic_events` — high/medium-impact prints in the next N days.
      * `earnings_calendar` — the ticker's next scheduled report.
      * `news_sentiment`   — articles in the last `news_lookback_days`
                             whose topics intersect catalyst tags AND
                             whose relevance >= 0.7. Surfaces the
                             actual M&A / earnings-beat headline that
                             drove the move (e.g. AVGO/Google deal).
      * `sec_filings`      — 8-Ks in the last `sec_lookback_days` with
                             material item codes (1.01 acquisition,
                             2.01 completion, 5.02 leadership change,
                             7.01 reg-FD selective disclosure, 8.01
                             other events).

    All four merged, deduped by (kind, date, name), sorted by date,
    capped at 8 entries (was 5 — news + SEC need more headroom).
    """
    today = as_of or datetime.now(timezone.utc).date()
    end = today + timedelta(days=lookahead_days)
    news_start = today - timedelta(days=news_lookback_days)
    sec_start = today - timedelta(days=sec_lookback_days)

    econ_sql = (
        "SELECT event_date, event_name, importance "
        "FROM economic_events "
        "WHERE event_date BETWEEN :start AND :end "
        "  AND importance IN ('high', 'medium') "
        "ORDER BY event_date ASC LIMIT 10"
    )
    econ_df = _query(econ_sql, {"start": str(today), "end": str(end)})

    earn_sql = (
        "SELECT earnings_date, company_name "
        "FROM earnings_calendar "
        "WHERE ticker = :ticker "
        "  AND earnings_date BETWEEN :start AND :end "
        "ORDER BY earnings_date ASC LIMIT 5"
    )
    earn_df = _query(
        earn_sql, {"ticker": ticker.upper(), "start": str(today), "end": str(end)}
    )

    # Catalyst-tagged news. Topics are stored as TEXT[] of AV's
    # snake_case slugs. Filter to high-conviction articles only.
    news_sql = (
        "SELECT published_ts, title, topics, relevance_score, "
        "       overall_sentiment_score, overall_sentiment_label "
        "FROM news_sentiment "
        "WHERE ticker = :ticker "
        "  AND published_ts >= CAST(:start AS timestamptz) "
        "  AND published_ts <= CAST(:end AS timestamptz) + INTERVAL '23 hours 59 minutes' "
        "  AND relevance_score >= 0.7 "
        "  AND topics && ARRAY['mergers_and_acquisitions','earnings','ipo','economy_monetary']::TEXT[] "
        "ORDER BY published_ts DESC LIMIT 6"
    )
    news_df = _query(
        news_sql,
        {"ticker": ticker.upper(), "start": str(news_start), "end": str(today)},
    )

    sec_sql = (
        "SELECT filing_date, form, items "
        "FROM sec_filings "
        "WHERE ticker = :ticker "
        "  AND form = '8-K' "
        "  AND filing_date >= CAST(:start AS date) "
        "  AND filing_date <= CAST(:end AS date) "
        "  AND items && ARRAY['1.01','2.01','5.02','7.01','8.01']::TEXT[] "
        "ORDER BY filing_date DESC LIMIT 5"
    )
    sec_df = _query(
        sec_sql,
        {"ticker": ticker.upper(), "start": str(sec_start), "end": str(today)},
    )

    out: list[dict] = []
    if econ_df is not None and not econ_df.empty:
        for _, r in econ_df.iterrows():
            out.append({
                "name": str(r["event_name"]),
                "date": str(r["event_date"]),
                "impact": str(r.get("importance") or "medium"),
                "kind": "economic",
            })
    if earn_df is not None and not earn_df.empty:
        for _, r in earn_df.iterrows():
            out.append({
                "name": f"Earnings — {r.get('company_name') or ticker.upper()}",
                "date": str(r["earnings_date"]),
                "impact": "high",
                "kind": "earnings",
            })
    if news_df is not None and not news_df.empty:
        for _, r in news_df.iterrows():
            rel = float(r.get("relevance_score") or 0.0)
            sent = float(r.get("overall_sentiment_score") or 0.0)
            # impact = high if both relevance + |sentiment| are strong
            if rel >= 0.9 and abs(sent) >= 0.4:
                impact = "high"
            elif rel >= 0.7 and abs(sent) >= 0.2:
                impact = "medium"
            else:
                impact = "low"
            title = str(r.get("title") or "")[:140]
            out.append({
                "name": title,
                "date": str(r["published_ts"])[:10],
                "impact": impact,
                "kind": "news_topic",
                # Forward sentiment so the Discord catalyst renderer
                # colours the dot by direction (🟢 bullish / 🔴 bearish
                # / 🟡 neutral) instead of impact-class colouring.
                "sentiment_score": sent,
            })
    if sec_df is not None and not sec_df.empty:
        # 8-K item code → human label. Material items only.
        ITEM_LABELS = {
            "1.01": "Material Definitive Agreement",
            "2.01": "Completed Acquisition / Disposition",
            "5.02": "Departure / Election of Officers",
            "7.01": "Regulation FD Disclosure",
            "8.01": "Other Events",
        }
        for _, r in sec_df.iterrows():
            items = r.get("items") or []
            labels = [ITEM_LABELS.get(it, it) for it in items if it in ITEM_LABELS]
            if not labels:
                continue
            # Highest impact: 1.01 / 2.01 (deal-related); others medium
            heavy = any(it in ("1.01", "2.01") for it in items)
            out.append({
                "name": f"8-K — {', '.join(labels)}",
                "date": str(r["filing_date"]),
                "impact": "high" if heavy else "medium",
                "kind": "sec_8k",
            })

    # Dedupe by (kind, date, name)
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for e in out:
        key = (e["kind"], e["date"], e["name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    deduped.sort(key=lambda e: e["date"])
    return {
        "available": True,
        "window_start": str(news_start),
        "window_end": str(end),
        "events": deduped[:8],
    }


# ---------------------------------------------------------------------------
# 7. News sentiment
# ---------------------------------------------------------------------------


def _default_lookback_hours_for(as_of: Optional[date_type]) -> int:
    """Pick the news lookback window so it bridges weekends.

    AV's NEWS_SENTIMENT coverage of small-cap ETFs (IWM family, plus
    most large-cap broad-market ETFs) is concentrated in three
    auto-publishers (富途牛牛, Moomoo, GuruFocus) that **only post on
    trading days**. Saturday and Sunday are routinely silent across the
    Russell 2000 family — verified empirically via the AV API.

    Result: a 48h lookback ending Mon 8:30 AM ET starts at Sat 8:30 AM
    ET — but Friday's last article posts ~4:10 PM ET = ~16h before that
    cutoff. Mondays would always have empty sentiment for these ETFs.

    Fix: bump the lookback to **72h on Mondays** (and Tuesday before
    market open, to be safe on long weekends) so Friday's late-day
    articles fall inside the window. Other weekdays stay at 48h.
    """
    if as_of is None:
        check_dt = datetime.now(timezone.utc)
    elif isinstance(as_of, datetime):
        check_dt = as_of
    else:
        # `date` — treat as midnight-end-of-day for weekday determination
        check_dt = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)

    # weekday(): 0=Mon .. 6=Sun
    if check_dt.weekday() == 0:  # Monday
        return 72
    return 48


def summarize_news_sentiment(
    ticker: str,
    as_of: Optional[date_type] = None,
    lookback_hours: Optional[int] = None,
) -> dict:
    """Aggregate recent news sentiment from the news_sentiment table.

    Returns headline counts, average sentiment score, and the top 5
    most relevant recent headlines. Lookback defaults to 48h on most
    weekdays, **72h on Mondays** to bridge the AV weekend gap (see
    `_default_lookback_hours_for` for the reasoning).
    """
    if lookback_hours is None:
        lookback_hours = _default_lookback_hours_for(as_of)
    if as_of is None:
        sql = (
            "SELECT title, sentiment_score, relevance_score, source, published_ts "
            "FROM news_sentiment "
            "WHERE ticker = :ticker "
            "  AND published_ts >= NOW() - (:hours || ' hours')::interval "
            "ORDER BY published_ts DESC"
        )
        params: dict[str, Any] = {"ticker": ticker.upper(), "hours": lookback_hours}
    else:
        # Datetime input is taken as the literal cutoff (point-in-time
        # replay). For a date-only input, advance to the start of the
        # *next* day so intraday articles on `as_of` are included
        # (str(date) resolves to midnight start).
        if isinstance(as_of, datetime):
            end_exclusive = as_of
        else:
            end_exclusive = as_of + timedelta(days=1)
        sql = (
            "SELECT title, sentiment_score, relevance_score, source, published_ts "
            "FROM news_sentiment "
            "WHERE ticker = :ticker "
            "  AND published_ts < CAST(:end_ts AS timestamptz) "
            "  AND published_ts >= CAST(:end_ts AS timestamptz) - (:hours || ' hours')::interval "
            "ORDER BY published_ts DESC"
        )
        params = {
            "ticker": ticker.upper(),
            "hours": lookback_hours,
            "end_ts": str(end_exclusive),
        }
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no news_sentiment rows for {ticker} in last {lookback_hours}h")

    scores = df["sentiment_score"].dropna().astype(float)
    relevances = df["relevance_score"].dropna().astype(float)

    bullish = int((scores > 0.15).sum())
    bearish = int((scores < -0.15).sum())
    neutral = int(len(scores)) - bullish - bearish
    avg_score = round(float(scores.mean()), 4) if not scores.empty else 0.0

    # Top 5 most relevant headlines
    top_df = df.nlargest(5, "relevance_score") if "relevance_score" in df.columns else df.head(5)
    headlines = [
        {
            "title": str(r.get("title", "")),
            "sentiment": round(float(r["sentiment_score"]), 3) if r.get("sentiment_score") is not None else None,
            "source": str(r.get("source", "")),
            "published": str(r.get("published_ts", "")),
        }
        for _, r in top_df.iterrows()
    ]

    return {
        "available": True,
        "lookback_hours": lookback_hours,
        "article_count": int(len(df)),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "avg_sentiment_score": avg_score,
        "headlines": headlines,
    }


# ---------------------------------------------------------------------------
# 8. Reflection memory (pgvector over journal_entries)
# ---------------------------------------------------------------------------


def retrieve_similar_journal(
    ticker: str, query_embedding: list[float], k: int = 5
) -> list[JournalRef]:
    """Find journal entries whose embedding is closest to the query.

    Uses pgvector cosine distance (`<=>`). Returns `JournalRef` objects
    (not raw rows) so downstream agents receive typed data.
    """
    if not query_embedding or len(query_embedding) == 0:
        return []

    # psycopg2 has no native pgvector adapter; serialize to text literal.
    vec_literal = format_vector_literal(query_embedding)
    sql = (
        "SELECT id::text AS id, ticker, direction, return_pct, "
        "       (embedding <=> :vec::vector) AS cosine_distance "
        "FROM journal_entries "
        "WHERE embedding IS NOT NULL AND ticker = :ticker "
        "ORDER BY embedding <=> :vec::vector ASC "
        "LIMIT :k"
    )
    df = _query(sql, {"vec": vec_literal, "ticker": ticker.upper(), "k": k})
    if df.empty:
        return []
    out: list[JournalRef] = []
    for _, row in df.iterrows():
        out.append(
            JournalRef(
                id=str(row["id"]),
                ticker=str(row["ticker"]),
                direction=str(row["direction"]),
                return_pct=(
                    float(row["return_pct"]) if row.get("return_pct") is not None else None
                ),
                cosine_distance=float(row["cosine_distance"]),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Bundle — one call to collect every section. Failed summaries are
# captured in `failed_sections` rather than raising.
# ---------------------------------------------------------------------------


def build_context_bundle(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Collect all summarizer outputs into one dict for analyst prompts.

    Each section is either a populated dict with `available: True` or
    `{available: False, reason: ...}`. A top-level `failed_sections`
    list tells the orchestrator which sections to mark degraded.
    """
    bundle = {
        "ticker": ticker.upper(),
        "as_of": str(as_of) if as_of else None,
    }
    sections = {
        "market": lambda: summarize_market_context(ticker, as_of),
        "strat": lambda: summarize_strat_status(ticker, as_of),
        "options": lambda: summarize_options_flow(ticker, as_of),
        "gamma": lambda: summarize_gamma_levels(ticker, as_of),
        "signals": lambda: summarize_signals_history(ticker, as_of=as_of),
        "backtest": lambda: summarize_backtest_metrics(ticker, as_of=as_of),
        "catalysts": lambda: summarize_catalysts(ticker, as_of),
        "sentiment": lambda: summarize_news_sentiment(ticker, as_of),
    }
    failed: list[str] = []
    for name, fn in sections.items():
        try:
            result = fn()
            bundle[name] = result
            if not result.get("available"):
                failed.append(name)
        except Exception as e:
            logger.exception("summarizer %s failed", name)
            bundle[name] = {"available": False, "reason": f"exception: {e}"}
            failed.append(name)
    bundle["failed_sections"] = failed
    return bundle
