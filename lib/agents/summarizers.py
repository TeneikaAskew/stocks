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


# Maximum trading-day gap between an options chain's snapshot_date and the
# brief's as-of date before we silence the options/gamma sections. The AV
# options fetcher writes EOD chains at ~21:00 ET; a Tuesday-morning brief
# reading Monday-EOD chain is 1 trading day behind and is the standard
# institutional convention. A Wednesday brief reading Friday-EOD chain
# (today's actual 5/13 state) is 3 trading days behind — strikes have
# rolled, expirations have been added, dealers have re-hedged. Citing
# Kings/Gates/Flip off that chain misleads the LLM and the reader.
#
# Used by `summarize_options_flow` (volume/OI/IV aggregates — still
# hard-silences at >2 trading days) and as the soft-warn boundary in
# `summarize_gamma_levels` (which now uses a tiered loader — see
# MAX_OPTIONS_HARD_STALE_TRADING_DAYS below).
MAX_OPTIONS_STALE_TRADING_DAYS = 2

# Hard cutoff for summarize_gamma_levels — beyond this, even the
# stale_fallback path returns `available: False`. Chosen at 5 trading days
# (one full trading week) because dealer positioning a week old is no
# longer a useful signal — strikes have rolled, expirations have been
# added, and the King/Gate map bears little relation to current spot.
# Added 2026-05-23 alongside the tiered realtime → EOD → stale loader
# in summarize_gamma_levels per docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md
# Track 1.
MAX_OPTIONS_HARD_STALE_TRADING_DAYS = 5


def _check_chain_freshness(
    chain_date,
    target_date=None,
    max_trading_days: int = MAX_OPTIONS_STALE_TRADING_DAYS,
) -> Optional[str]:
    """Return None when fresh, or a string reason when stale.

    Uses `numpy.busday_count` (Mon-Fri, no holiday awareness) which is
    close enough for staleness — false-flag on the rare Tuesday-after-
    Monday-holiday is acceptable defensive behavior.

    Accepts either `date` or `datetime` for both inputs and coerces to
    `.date()` before counting. `parse_as_of` returns timezone-aware
    `datetime` when `INSIGHT_AS_OF` is a full ISO timestamp; passing
    that straight to `np.busday_count` would raise.
    """
    if isinstance(chain_date, datetime):
        chain_date = chain_date.date()
    target = target_date if target_date else date_type.today()
    if isinstance(target, datetime):
        target = target.date()
    trading_days = int(np.busday_count(chain_date, target))
    if trading_days > max_trading_days:
        return (
            f"chain stale: {trading_days} trading days behind {target} "
            f"(snapshot_date={chain_date})"
        )
    return None


def classify_gamma_freshness(days_behind: int) -> str:
    """Map a trading-day gap to a Track 1 data_source tier.

    Returns one of:
      'eod_fallback'    — 0-2 trading days behind (institutional norm)
      'stale_fallback'  — 3-5 trading days behind (warn but still serve)
      'unavailable'     — >5 trading days behind (hard silence)

    Shared between `summarize_gamma_levels` (which runs the full GEX
    math) and the premarket-brief freshness footer (which probes only
    the snapshot metadata) so the two paths can never disagree on
    which tier a given chain falls into.
    """
    if days_behind > MAX_OPTIONS_HARD_STALE_TRADING_DAYS:
        return "unavailable"
    if days_behind > MAX_OPTIONS_STALE_TRADING_DAYS:
        return "stale_fallback"
    return "eod_fallback"


# ---------------------------------------------------------------------------
# 1. Market context
# ---------------------------------------------------------------------------


def summarize_market_context(
    ticker: str, as_of: Optional[date_type] = None,
    inclusive_today: bool = False,
) -> dict:
    """Daily OHLCV + indicators + regime classification.

    Reads market_data_daily for the row at or before `as_of` (default:
    latest). Computes a regime tag (trending up/down/ranging) and a
    20-day realized vol tag (low/normal/elevated).

    Replay semantics (when ``as_of`` is set):
      Daily / indicator columns come from the latest row STRICTLY
      BEFORE ``as_of`` — i.e. yesterday's completed bar — because on a
      live 8:45 AM ET run today's row exists with NULL close (the
      11 PM ET fetcher hasn't run yet). Reading today's row in a
      replay leaks the post-RTH close into the trade_planner's
      ``cleared_above`` calculation and forces blue-sky synthesis on
      otherwise-normal days. The 5/6 QQQ replay surfaced this:
      AS-OF=5/6 was reading 5/6's RTH close (~$693), comparing PDH
      ($682.77) below it, and synthesizing a $695 entry that the
      live 8:45 AM run on 5/6 would never have produced.

      Pre-market columns (pre_high, pre_low, pre_vwap, pre_volume,
      gap_pct, pre_range_atr) DO come from today's row (= as_of),
      because the 8:30 AM ET fetcher populates those fields before
      the insight pipeline runs at 8:45 AM. Yesterday's pre_high
      would be a day-old reading.

    ``inclusive_today`` (added to make the contract explicit):
      Default False — premarket contract used by the insight pipeline.
      Set True for EOD / backtest contexts that want to read today's
      completed daily row.
    """
    daily_op = "<=" if inclusive_today else "<"
    daily_sql = (
        "SELECT date, open, high, low, close, volume, "
        "       sma_200, ema_20, ema_50, rsi_14, macd, macd_signal, "
        "       macd_histogram, bb_upper, bb_lower, bb_pct, atr_14, "
        "       rvol, volatility_20d, price_vs_ema20, "
        "       pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr "
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        + (f"AND date {daily_op} :as_of " if as_of else "")
        + "ORDER BY date DESC LIMIT 1"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(daily_sql, params)
    if df.empty:
        return _unavailable(f"no market_data_daily row for {ticker}")

    row = df.iloc[0]

    # On replay, overlay today's pre_* columns (today's row exists at
    # 8:45 AM ET via the premarket fetcher, with daily OHLC still NULL).
    if as_of:
        pm_df = _query(
            "SELECT pre_high, pre_low, pre_vwap, pre_volume, gap_pct, "
            "       pre_range_atr "
            "FROM market_data_daily "
            "WHERE ticker = :ticker AND date = :as_of LIMIT 1",
            {"ticker": ticker.upper(), "as_of": str(as_of)},
        )
        if not pm_df.empty:
            pm_row = pm_df.iloc[0]
            row = row.copy()
            for col in (
                "pre_high", "pre_low", "pre_vwap", "pre_volume",
                "gap_pct", "pre_range_atr",
            ):
                if col in pm_row.index:
                    row[col] = pm_row[col]

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
    ticker: str, as_of: Optional[date_type] = None,
    inclusive_today: bool = True,
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

    ``inclusive_today`` forwards to compute_strat_status — see its
    docstring. Default True for backwards-compat; the insight pipeline
    passes False (premarket context: today's daily row excluded).
    """
    from lib.strat import compute_strat_status

    status = compute_strat_status(ticker, as_of=as_of,
                                  inclusive_today=inclusive_today)
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
                # Match the cutoff semantic used inside compute_strat_status:
                #   inclusive_today=True  → df.index <= cutoff (backtest contract)
                #   inclusive_today=False → df.index < midnight-of-cutoff-date
                #                          (premarket contract — exclude entire as_of date)
                if inclusive_today:
                    df = df[df.index <= cutoff]
                else:
                    df = df[df.index < cutoff.normalize()]
            # PR #400 fix applied to this code path: pass analysis_date so
            # compute_previous_levels uses period-filter semantics ("the
            # period BEFORE the period containing analysis_date") instead
            # of the legacy iloc[-2] fallback that assumes df's last row
            # is today's in-progress bar. Without this, the bundle showed
            # 5/4's H/L as PDH/PDL on a 2026-05-06 replay because the df
            # had already been pre-filtered to exclude 5/6 — iloc[-2]
            # then picked 5/4 instead of 5/5. PR #400 fixed this for the
            # brief + playbook_resolver; this code path was missed.
            analysis_date_for_levels = None
            if as_of is not None:
                import pandas as _pd
                _ts = _pd.Timestamp(as_of)
                if _ts.tz is not None:
                    _ts = _ts.tz_convert('UTC').tz_localize(None)
                analysis_date_for_levels = _ts.date()
            level_map = compute_previous_levels(
                df, analysis_date=analysis_date_for_levels
            )
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
    ticker: str, as_of: Optional[date_type] = None,
    inclusive_today: bool = True,
) -> dict:
    """Latest AlphaVantage EOD options chain snapshot aggregates.

    Returns total call/put volume, put/call ratio, max-pain strike,
    top open-interest strikes, and weighted average IV.

    ``inclusive_today``:
      All etf_options_snapshots rows are taken at 19:00 ET (post-close).
      The DB has exactly one snapshot per (ticker, snapshot_date).
      - True (default): WHERE snapshot_date <= as_of — admits as_of's
        EOD snapshot. Use for EOD analytics or "what would the chain
        look like at end of day X" semantics.
      - False (premarket contract): WHERE snapshot_date < as_of —
        excludes as_of's EOD snapshot entirely. The latest snapshot
        the brief / insight pipeline can legitimately see at 8:30 AM
        ET on as_of is the prior trading day's 19:00 ET snapshot.
    """
    snap_op = "<=" if inclusive_today else "<"
    sql = (
        "SELECT option_type, strike, volume, open_interest, "
        "       implied_volatility, delta, snapshot_date "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        + (f"AND snapshot_date {snap_op} :as_of " if as_of else "")
        + "  AND snapshot_date = ("
        "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker AND data_source = 'alphavantage'"
        + (f"      AND snapshot_date {snap_op} :as_of" if as_of else "")
        + "  )"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no etf_options_snapshots for {ticker}")

    chain_date_raw = df["snapshot_date"].iloc[0]
    chain_date = chain_date_raw.date() if hasattr(chain_date_raw, "date") else pd.to_datetime(chain_date_raw).date()
    stale_reason = _check_chain_freshness(chain_date, as_of)
    if stale_reason:
        return _unavailable(stale_reason)

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
    ticker: str, as_of: Optional[date_type] = None,
    inclusive_today: bool = True,
) -> dict:
    """Stratalyst-style gamma analytics: King / Gate / Spot / Flip + regime.

    Tiered loader (added 2026-05-23 per Track 1 of
    docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md, after the AV
    subscription upgrade exposed REALTIME_OPTIONS):

      1. REALTIME — most recent intraday snapshot from
         etf_options_snapshots WHERE market_session='REALTIME' (writes
         from fetch_av_realtime_options.py every 5 min during RTH).
      2. EOD fallback (≤2 trading days old) — most recent snapshot
         WHERE market_session='EOD' (writes from
         fetch_av_historical_options.py nightly at ~21:00 ET). The
         standard institutional convention; a Tuesday-morning brief
         reading Monday-EOD chain is 1 trading day behind = fresh.
      3. Stale fallback (3-5 trading days old) — same EOD path but
         flagged so the consumer can warn the user. The 3-day cliff
         used to silence the section entirely; now we surface it with
         a `stale_fallback` marker so dealer walls are still visible
         after long weekends or fetcher outages.
      4. Hard stale (>5 trading days) — returns `{available: False}`.

    The return dict adds two fields beyond the pre-Track-1 contract:

      - `data_source`: 'realtime' | 'eod_fallback' | 'stale_fallback'
      - `snapshot_ts`:  ISO-formatted timestamp of the underlying
                        snapshot (REALTIME → intraday wall-clock;
                        EOD → ~21:00 ET nightly)

    Consumers (premarket brief, gamma analyst prompt, key_levels glue)
    use these to render a freshness footer and to caveat any analyst
    language that would otherwise read intraday repositioning into
    yesterday's static EOD chain.

    Any consumer wanting a richer response should call the
    /api/options/{ticker}/{date}/levels endpoint directly instead of
    consuming this summary.

    ``inclusive_today`` mirrors summarize_options_flow — see its
    docstring. False = premarket contract (no as_of-dated snapshots);
    True = include today's snapshots (insight pipeline live runs).
    """
    from lib import gamma  # local import to avoid circular at module load

    snap_op = "<=" if inclusive_today else "<"
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)

    # Phase 1: try REALTIME — pull all rows of the latest intraday
    # snapshot_ts. The unique key (ticker, snapshot_ts, option_type,
    # expiration, strike) guarantees one snapshot_ts == one full chain.
    realtime_sql = (
        "SELECT option_type, strike, expiration, "
        "       open_interest, gamma, vega, delta, "
        "       bid, ask, mark, last_price, snapshot_date, snapshot_ts "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        "  AND market_session = 'REALTIME' "
        + (f"AND snapshot_date {snap_op} :as_of " if as_of else "")
        + "  AND snapshot_ts = ("
        "      SELECT MAX(snapshot_ts) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker "
        "        AND data_source = 'alphavantage' "
        "        AND market_session = 'REALTIME'"
        + (f"      AND snapshot_date {snap_op} :as_of" if as_of else "")
        + "  )"
    )
    df = _query(realtime_sql, params)

    data_source: Optional[str] = None
    if not df.empty:
        data_source = "realtime"
    else:
        # Phase 2: fall back to EOD. The OR-NULL clause handles the
        # historical rows written before market_session was populated
        # (pre-Track-0 EOD writes set it explicitly; older rows are
        # NULL but still 'EOD' semantically).
        eod_sql = (
            "SELECT option_type, strike, expiration, "
            "       open_interest, gamma, vega, delta, "
            "       bid, ask, mark, last_price, snapshot_date, snapshot_ts "
            "FROM etf_options_snapshots "
            "WHERE ticker = :ticker "
            "  AND data_source = 'alphavantage' "
            "  AND (market_session = 'EOD' OR market_session IS NULL) "
            + (f"AND snapshot_date {snap_op} :as_of " if as_of else "")
            + "  AND snapshot_date = ("
            "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
            "      WHERE ticker = :ticker "
            "        AND data_source = 'alphavantage' "
            "        AND (market_session = 'EOD' OR market_session IS NULL)"
            + (f"      AND snapshot_date {snap_op} :as_of" if as_of else "")
            + "  )"
        )
        df = _query(eod_sql, params)
        if df.empty:
            return _unavailable(f"no etf_options_snapshots for {ticker}")

        # Tier the EOD snapshot into eod_fallback / stale_fallback /
        # hard-stale based on trading-day gap.
        chain_date_raw = df["snapshot_date"].iloc[0]
        chain_date = (
            chain_date_raw.date() if hasattr(chain_date_raw, "date")
            else pd.to_datetime(chain_date_raw).date()
        )
        target = as_of if as_of else date_type.today()
        if isinstance(target, datetime):
            target = target.date()
        days_behind = int(np.busday_count(chain_date, target))
        data_source = classify_gamma_freshness(days_behind)
        if data_source == "unavailable":
            return _unavailable(
                f"chain hard-stale: {days_behind} trading days behind {target} "
                f"(snapshot_date={chain_date})"
            )

    # Snapshot timestamp for the freshness footer / analyst prompt.
    # Falls back to snapshot_date midnight if a row predates the
    # snapshot_ts column (shouldn't happen — schema has NOT NULL — but
    # defensive against rows backfilled with synthetic ts).
    snapshot_ts_raw = (
        df["snapshot_ts"].iloc[0] if "snapshot_ts" in df.columns
        else df["snapshot_date"].iloc[0]
    )
    snapshot_ts_iso = (
        snapshot_ts_raw.isoformat() if hasattr(snapshot_ts_raw, "isoformat")
        else str(snapshot_ts_raw)
    )

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
        "data_source": data_source,
        "snapshot_ts": snapshot_ts_iso,
        "spot": round(summary.spot.price, 2),
        "spot_method": summary.spot.method,
        "gamma_balance": round(summary.gamma_balance, 2) if summary.gamma_balance else None,
        "gamma_flip": round(summary.gamma_flip, 2) if summary.gamma_flip else None,
        "regime": summary.regime,
        "total_gex": round(summary.total_gex, 0),
        "kings": [_level_brief(lv) for lv in summary.kings[:3]],
        "gates": [_level_brief(lv) for lv in summary.gates[:5]],
        "gamma_balance_levels": [_level_brief(lv) for lv in summary.gamma_balance_levels],
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

    NOT called by `build_insight_bundle` as of 2026-05-11 — feeding
    signal_alerts into the LLM bundle creates a self-reinforcing
    feedback loop with signal-monitor (which gates on the insight
    pipeline's `insight_direction`). See the comment on the `sections`
    dict in `build_insight_bundle` for the full rationale.

    Kept callable so external analytics scripts, ad-hoc debugging, and
    the `signal-monitor-eod-resolver` pipeline can still aggregate the
    history. Do NOT re-add this back to the bundle without addressing
    the circular dependency.

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
    #
    # When the morning insight cron fires (8:45 AM ET = 12:45 UTC) the
    # daily fetcher may have written a pre-RTH-close placeholder for
    # the current trading day with NaN volume/RSI/etc. — see the
    # premarket-placeholder pattern that PR #323 (G.P0.3) addressed
    # for audit_data_freshness. If the literal-latest row has missing
    # indicators, walk back to the most recent COMPLETE bar so we use
    # yesterday's-close pattern as "today" rather than failing the
    # whole section. Audit 2026-05-08 G.P2.13 — backtest was failing
    # 9/24 reports (37.5 %) on Mon/Wed/Fri runs vs 0 on Tue/Thu, the
    # exact pattern a placeholder-row hypothesis predicts.
    needed_cols = ["gap_pct", "vol_ratio", "rsi_14", "close_vs_sma200_pct"]
    completeness = df[needed_cols].notna().all(axis=1)
    complete_rows = df.loc[completeness]
    if complete_rows.empty:
        return _unavailable(
            f"no complete daily bars for {ticker} — every row has at "
            f"least one missing indicator feature"
        )
    today = complete_rows.iloc[-1]
    pattern_is_proxy = today["date"] != df.iloc[-1]["date"]

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
            "pattern_is_proxy": pattern_is_proxy,
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
        "pattern_is_proxy": pattern_is_proxy,
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
        # Audit 2026-05-08 G.P2.13: empty news is the COMMON case for
        # less-traded tickers (IWM had only 3 articles across 30 days
        # in May 2026). Don't fail the whole section — return an
        # available-but-empty payload so the analyst can write
        # "no recent news for $TICKER" rather than the orchestrator
        # marking the section failed and degrading downstream debate.
        return {
            "available": True,
            "lookback_hours": lookback_hours,
            "article_count": 0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "avg_sentiment_score": 0.0,
            "headlines": [],
            "note": (
                f"no news_sentiment rows for {ticker} in last "
                f"{lookback_hours}h — sparse-coverage ticker"
            ),
        }

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
    ticker: str, as_of: Optional[date_type] = None,
    inclusive_today: bool = False,
) -> dict:
    """Collect all summarizer outputs into one dict for analyst prompts.

    Each section is either a populated dict with `available: True` or
    `{available: False, reason: ...}`. A top-level `failed_sections`
    list tells the orchestrator which sections to mark degraded.

    ``inclusive_today`` (default False): premarket contract. Today's
    daily bar is excluded from market_context + strat_status because
    on a live 8:30 AM ET / replay-of-8:30 AM run, today's RTH bar
    either doesn't exist yet (live) or would be look-ahead (replay).
    Set True only for explicit EOD analytics that *want* today's
    closed bar.
    """
    bundle = {
        "ticker": ticker.upper(),
        "as_of": str(as_of) if as_of else None,
    }
    sections = {
        "market": lambda: summarize_market_context(ticker, as_of, inclusive_today=inclusive_today),
        "strat": lambda: summarize_strat_status(ticker, as_of, inclusive_today=inclusive_today),
        "options": lambda: summarize_options_flow(ticker, as_of, inclusive_today=inclusive_today),
        "gamma": lambda: summarize_gamma_levels(ticker, as_of, inclusive_today=inclusive_today),
        # NOTE: `signals` (signal_alerts history) is deliberately NOT in
        # the LLM bundle. signal-monitor uses the insight pipeline's
        # `insight_direction` as a firing gate (PR #419, "Phase 1
        # insight direction gate"), so feeding signal_alerts back into
        # the LLM creates a self-reinforcing feedback loop: insight
        # decides direction → signal-monitor fires alerts in that
        # direction → next insight run reads those alerts → confirms
        # the same direction → repeat.
        # Observed 2026-05-11: gemini-3.1-flash-lite committed to
        # SHORT/medium on SPY based on 5 fresh weak PUT alerts (all
        # exited time_stop with avg return -0.05%), even though
        # ftfc_direction was bullish. summarize_signals_history()
        # remains callable for external analytics / debugging, but
        # the insight prompt no longer sees it.
        "backtest": lambda: summarize_backtest_metrics(ticker, as_of=as_of),
        "catalysts": lambda: summarize_catalysts(ticker, as_of),
        "sentiment": lambda: summarize_news_sentiment(ticker, as_of),
    }
    failed: list[str] = []
    failed_reasons: dict[str, str] = {}
    for name, fn in sections.items():
        try:
            result = fn()
            bundle[name] = result
            if not result.get("available"):
                failed.append(name)
                # Audit 2026-05-08 G.P2.13: surface the section's own
                # `reason` so the orchestrator can persist it on the
                # report rather than burying it in Cloud Logs only.
                reason = result.get("reason")
                if isinstance(reason, str) and reason:
                    failed_reasons[name] = reason
        except Exception as e:
            logger.exception("summarizer %s failed", name)
            bundle[name] = {"available": False, "reason": f"exception: {e}"}
            failed.append(name)
            failed_reasons[name] = f"exception: {type(e).__name__}: {e}"
    bundle["failed_sections"] = failed
    bundle["failed_section_reasons"] = failed_reasons
    return bundle
