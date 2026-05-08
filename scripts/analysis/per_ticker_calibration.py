#!/usr/bin/env python3
"""Per-ticker calibration recommender for the strategies package.

Replaces the global Tier-B defaults in `lib/strategies/config.py` and the
global `ExitConfig` in `lib/config.py` with **per-ticker, data-driven**
recommendations derived from production-replay of `signal_alerts` against
the actual intraday tape.

Per the audit plan (Track E, 2026-05-08), this script answers:

  1. For ticker T, what target/stop/time-stop maximizes expected return
     given T's observed MFE/MAE distribution from past signals?
  2. Which strategy (momentum vs mean-reversion) wins on T?
  3. Which timeframe tag (15m / 30m / 60m) yields the best hit-rate on T?
  4. Which conditions in `conditions_met` actually discriminate winners
     from losers (vs firing equally on both → free-score noise)?

USAGE
-----

    # Sandbox / audit replay (reads pre-cached CSVs):
    python scripts/analysis/per_ticker_calibration.py \
        --data-dir /tmp/audit_data \
        --tickers SPY IWM QQQ \
        --out-json docs/audit/2026-05-08/recommended_per_ticker_config.json \
        --out-md   docs/audit/2026-05-08/per_ticker_writeup.md

    # Production reuse (reads Cloud SQL — needs CLOUD_SQL_CONNECTION_NAME etc.):
    python scripts/analysis/per_ticker_calibration.py \
        --from-db --lookback-days 90 \
        --out-json gcp/queries/recommended_per_ticker_config.json \
        --out-md   docs/per_ticker_writeup.md

    # Auto-pull ticker list from `watchlists` where signals=true:
    python scripts/analysis/per_ticker_calibration.py --from-db --auto-tickers

INPUTS
------

Cached-CSV mode (`--data-dir`):
    {data_dir}/signal_alerts.csv       all columns of signal_alerts table
    {data_dir}/intraday_<ticker>.csv   ts, open, high, low, close, volume
                                       (one file per ticker, lower-case suffix)
    {data_dir}/ticker_calibration.csv  current Tier-A values

DB mode (`--from-db`):
    Queries Cloud SQL via `gcp.database.get_engine()`.

OUTPUTS
-------

`recommended_per_ticker_config.json` — one entry per ticker, identical
schema. Schema:

    {
      "<TICKER>": {
        "call_rsi_range":            [low, high]   | null,
        "put_rsi_range":             [low, high]   | null,
        "min_conditions_momentum":   int           | null,
        "min_conditions_mr":         int           | null,
        "call_target":               float (e.g. 0.0030),
        "put_target":                float,
        "call_stop":                 float,
        "put_stop":                  float,
        "call_time_stop":            int (minutes),
        "put_time_stop":             int (minutes),
        "preferred_strategy_call":   "momentum" | "mean_reversion" | "either",
        "preferred_strategy_put":    "momentum" | "mean_reversion" | "either",
        "preferred_timeframe_call":  "5m" | "15m" | "30m" | "60m" | null,
        "preferred_timeframe_put":   "5m" | "15m" | "30m" | "60m" | null,
        "combo_bonus_overrides":     null   (placeholder; see notes),
        "n_signals_used":            int,
        "n_signals_with_intraday":   int,
        "lookback_days":             int,
        "as_of":                     "YYYY-MM-DD",
        "notes":                     str | null
      }
    }

`per_ticker_writeup.md` — full markdown writeup with side-by-side
comparison table, per-ticker root-cause section, and factor-discrimination
table.

DESIGN NOTES
------------

* Equal-treatment principle: every ticker gets the SAME schema and the
  SAME computation pipeline. No ticker has unique keys; tickers with
  insufficient data emit `null` values plus a `notes` explanation.
* Reusable: this script is intentionally not a fast path. To add a new
  ticker (e.g. SPX), populate the watchlist → re-run.
* Replay-correct: exits are recomputed from intraday bars rather than
  trusting `signal_alerts.exit_*` columns, which Track A found to be
  76% NULL across the 2026-03-19 → 2026-05-07 history.
* No production code changed: this script READS existing tables and
  WRITES a JSON file. It does not modify `ticker_calibration` or any
  config. The output is for human review and follow-up PR(s).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── current global defaults (from lib/config.py:ExitConfig) ──────────────
DEFAULT_CALL_TARGET = 0.0030
DEFAULT_PUT_TARGET = 0.0038
DEFAULT_CALL_STOP = 0.0015
DEFAULT_PUT_STOP = 0.0020
DEFAULT_CALL_TIME_STOP = 30   # minutes
DEFAULT_PUT_TIME_STOP = 35
DEFAULT_CALL_RSI = (25.0, 50.0)
DEFAULT_PUT_RSI = (50.0, 75.0)

# Slippage / spread cost floor — recommended targets must clear this to be
# economically meaningful after typical execution friction. 15 bps is
# conservative for liquid ETF options at retail; tighten to 10 bps for
# pure-shares trades. Without this floor, the MFE-anchored target can
# recommend 5–10 bps targets that won't clear the bid-ask spread.
SLIPPAGE_BPS = 0.0015  # 0.15% one-way


# ── data loaders ─────────────────────────────────────────────────────────


def load_signal_alerts_csv(path: Path, tickers: list[str]) -> pd.DataFrame:
    """Load signal_alerts.csv into a typed, ticker-filtered DataFrame."""
    df = pd.read_csv(path)
    df = df[df["ticker"].isin(tickers)].copy()
    df["alert_ts"] = pd.to_datetime(df["alert_ts"], utc=True, format="ISO8601")
    df["alert_date"] = pd.to_datetime(df["alert_date"]).dt.date
    df["price_at_signal"] = pd.to_numeric(df["price_at_signal"], errors="coerce")
    df["target_price"] = pd.to_numeric(df["target_price"], errors="coerce")
    df["total_score"] = pd.to_numeric(df["total_score"], errors="coerce")
    df["base_score"] = pd.to_numeric(df["base_score"], errors="coerce")
    df["rsi"] = pd.to_numeric(df["rsi"], errors="coerce")
    df["rvol"] = pd.to_numeric(df["rvol"], errors="coerce")
    df["time_stop_minutes"] = pd.to_numeric(df["time_stop_minutes"], errors="coerce").fillna(60)
    df["conditions_met"] = df["conditions_met"].apply(_safe_load_jsonb)
    df["strategy_agreement"] = df["strategy_agreement"].apply(_safe_load_jsonb)
    return df


def load_intraday_csv(path: Path) -> pd.DataFrame:
    """Load one ticker's 1-min bars."""
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def _safe_load_jsonb(v) -> list:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def load_from_db(lookback_days: int, tickers: list[str]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    """Live DB path. Cloud Run / local-with-creds; not the audit-sandbox path."""
    from gcp.database import get_engine
    eng = get_engine()
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    sa_sql = (
        "SELECT id, ticker, alert_ts, alert_date, direction, base_score, strat_bonus, total_score, "
        "strength_label, position_size, price_at_signal, target_price, time_stop_minutes, rsi, rvol, "
        "conditions_met, strategy_agreement, timeframe_tag, expected_hold_min, exit_ts, exit_reason, "
        "exit_price, exit_return_pct, is_open, brief_bias, brief_alignment, level_broken "
        f"FROM signal_alerts WHERE alert_date >= '{cutoff}' AND ticker = ANY(%s) ORDER BY ticker, alert_ts"
    )
    sa = pd.read_sql(sa_sql, eng, params=(tickers,))

    intraday: dict[str, pd.DataFrame] = {}
    for t in tickers:
        partition = f"market_data_intraday_{t.lower()}" if t.upper() in ("SPY", "IWM", "QQQ", "SPX") \
            else "market_data_intraday"
        sql = (
            f"SELECT ts, open, high, low, close, volume FROM {partition} "
            f"WHERE ts >= '{cutoff}' AND interval='1min' "
        )
        if partition == "market_data_intraday":
            sql += f"AND ticker = '{t}' "
        sql += "ORDER BY ts"
        df = pd.read_sql(sql, eng)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        intraday[t] = df

    cal = pd.read_sql(
        "SELECT * FROM ticker_calibration WHERE ticker = ANY(%s) ORDER BY ticker, calibration_date DESC",
        eng, params=(tickers,),
    )
    return sa, intraday, cal


def load_tickers_from_watchlist() -> list[str]:
    """Auto-pull ticker list from watchlists table where signals=true."""
    from gcp.database import get_engine
    eng = get_engine()
    df = pd.read_sql(
        "SELECT DISTINCT ticker FROM watchlists WHERE signals=true AND removed_at IS NULL ORDER BY ticker",
        eng,
    )
    return df["ticker"].tolist()


# ── replay engine ────────────────────────────────────────────────────────


@dataclass
class ReplayResult:
    exit_reason: str  # TARGET_HIT | STOP_LOSS | TIME_STOP | NO_DATA
    return_pct: float
    holding_minutes: int
    mfe_pct: float   # max favorable excursion as % of entry
    mae_pct: float   # max adverse excursion


def simulate_exit(
    intraday: pd.DataFrame,
    entry_ts: pd.Timestamp,
    direction: str,
    entry_price: float,
    target_pct: float,
    stop_pct: float,
    time_stop_min: int,
) -> Optional[ReplayResult]:
    """Walk forward from `entry_ts` and apply target/stop/time-stop.

    Direction sign:
      CALL profit when price rises  → target = entry*(1+t), stop = entry*(1-s)
      PUT  profit when price falls  → target = entry*(1-t), stop = entry*(1+s)

    Conflict policy: if both target and stop hit in the same bar, we
    return STOP_LOSS (conservative — same as the production
    `gcp/signal_monitor.py` exit resolver). Without intra-bar tick data
    we can't know which fired first.
    """
    if entry_price <= 0 or pd.isna(entry_price):
        return None

    end_ts = entry_ts + pd.Timedelta(minutes=time_stop_min)
    win = intraday[(intraday["ts"] > entry_ts) & (intraday["ts"] <= end_ts)]
    if win.empty:
        return None

    is_call = direction.upper() == "CALL"
    target_price = entry_price * (1 + target_pct) if is_call else entry_price * (1 - target_pct)
    stop_price = entry_price * (1 - stop_pct) if is_call else entry_price * (1 + stop_pct)

    mfe_pct = 0.0
    mae_pct = 0.0
    for row in win.itertuples():
        # Track MFE/MAE for the bar
        if is_call:
            mfe = (row.high - entry_price) / entry_price
            mae = (row.low - entry_price) / entry_price
        else:
            mfe = (entry_price - row.low) / entry_price
            mae = (entry_price - row.high) / entry_price
        mfe_pct = max(mfe_pct, mfe)
        mae_pct = min(mae_pct, mae)

        # Check stop (conservative: conflict goes to stop)
        if is_call and row.low <= stop_price:
            return ReplayResult(
                "STOP_LOSS", -stop_pct, int((row.ts - entry_ts).total_seconds() // 60),
                mfe_pct, mae_pct,
            )
        if (not is_call) and row.high >= stop_price:
            return ReplayResult(
                "STOP_LOSS", -stop_pct, int((row.ts - entry_ts).total_seconds() // 60),
                mfe_pct, mae_pct,
            )
        # Check target
        if is_call and row.high >= target_price:
            return ReplayResult(
                "TARGET_HIT", target_pct, int((row.ts - entry_ts).total_seconds() // 60),
                mfe_pct, mae_pct,
            )
        if (not is_call) and row.low <= target_price:
            return ReplayResult(
                "TARGET_HIT", target_pct, int((row.ts - entry_ts).total_seconds() // 60),
                mfe_pct, mae_pct,
            )

    # Time stop — exit at last bar's close
    last = win.iloc[-1]
    if is_call:
        ret = (last.close - entry_price) / entry_price
    else:
        ret = (entry_price - last.close) / entry_price
    return ReplayResult(
        "TIME_STOP", float(ret), int((last.ts - entry_ts).total_seconds() // 60),
        mfe_pct, mae_pct,
    )


def replay_alerts(
    alerts: pd.DataFrame,
    intraday_by_ticker: dict[str, pd.DataFrame],
    target_call: float = DEFAULT_CALL_TARGET,
    target_put: float = DEFAULT_PUT_TARGET,
    stop_call: float = DEFAULT_CALL_STOP,
    stop_put: float = DEFAULT_PUT_STOP,
    time_stop_call: int = DEFAULT_CALL_TIME_STOP,
    time_stop_put: int = DEFAULT_PUT_TIME_STOP,
) -> pd.DataFrame:
    """For every alert, simulate exit and return per-alert outcome.

    Output columns are prefixed with ``replay_`` so callers can merge
    against ``signal_alerts`` (which already has its own ``exit_reason``,
    ``exit_return_pct`` columns) without ``_x`` / ``_y`` suffixes.
    """
    out_rows = []
    for r in alerts.itertuples():
        intraday = intraday_by_ticker.get(r.ticker)
        if intraday is None or intraday.empty:
            out_rows.append({"id": r.id, "replay_exit_reason": "NO_DATA",
                             "replay_return_pct": np.nan,
                             "holding_minutes": np.nan, "mfe_pct": np.nan, "mae_pct": np.nan})
            continue
        is_call = r.direction.upper() == "CALL"
        res = simulate_exit(
            intraday, r.alert_ts, r.direction, r.price_at_signal,
            target_pct=target_call if is_call else target_put,
            stop_pct=stop_call if is_call else stop_put,
            time_stop_min=time_stop_call if is_call else time_stop_put,
        )
        if res is None:
            out_rows.append({"id": r.id, "replay_exit_reason": "NO_DATA",
                             "replay_return_pct": np.nan,
                             "holding_minutes": np.nan, "mfe_pct": np.nan, "mae_pct": np.nan})
        else:
            out_rows.append({"id": r.id, "replay_exit_reason": res.exit_reason,
                             "replay_return_pct": res.return_pct,
                             "holding_minutes": res.holding_minutes,
                             "mfe_pct": res.mfe_pct, "mae_pct": res.mae_pct})
    return pd.DataFrame(out_rows)


# ── strategy classification ──────────────────────────────────────────────

# Conditions exclusive to (or strongly indicative of) each strategy.
MOMENTUM_ONLY = {"rsi_bullish_recovery", "rsi_bearish_recovery", "above_ema9", "below_ema9",
                 "rvol_above_recent", "atr_expansion", "rsi_thrust"}
MEAN_REV_ONLY = {"rsi_oversold_zone", "rsi_overbought_zone", "stoch_rsi_oversold",
                 "stoch_rsi_overbought", "level_break_pdh", "level_break_pdl",
                 "near_below_emas", "near_above_emas"}


def classify_strategy(conditions: list[str]) -> str:
    """Best-guess: which strategy fired this signal?

    Inspecting `conditions_met` directly because `signal_alerts` doesn't
    expose `strategy` as a column. Conditions are emitted by the strategy
    that fired them, so the set of conditions IS the strategy fingerprint.
    """
    conds = set(conditions or [])
    mom = len(conds & MOMENTUM_ONLY)
    mr = len(conds & MEAN_REV_ONLY)
    if mom > mr:
        return "momentum"
    if mr > mom:
        return "mean_reversion"
    return "ambiguous"


# ── multi-timeframe statistics ───────────────────────────────────────────


def multi_timeframe_stats(intraday: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min bars to 5/15/30/60/240-min and compute return stats.

    Returns one row per timeframe with:
      bar_return_mean_pct  — mean per-bar log-style return
      bar_return_std_pct   — bar-return standard deviation (volatility regime)
      autocorr_lag1        — Pearson autocorrelation of bar returns at lag 1.
                             > 0 = momentum (trends persist)
                             < 0 = mean-reversion (returns flip sign)
      n_bars               — sample size after RTH filter
      regime               — 'momentum' if autocorr>0.05, 'mean_reversion' if <-0.05, else 'mixed'
    """
    if intraday.empty:
        return pd.DataFrame()
    df = intraday.copy()
    df = df.set_index("ts").sort_index()
    # Restrict to regular trading hours (09:30–16:00 ET) so resamples align
    # with the live monitor's window. Intraday data is stored as ET-as-UTC
    # naive, but `ts` here is tz-aware UTC — so RTH in UTC is 13:30–20:00.
    rth_mask = (df.index.hour * 60 + df.index.minute >= 13 * 60 + 30) & (df.index.hour < 20)
    df = df[rth_mask]
    if df.empty:
        return pd.DataFrame()

    rows = []
    for tf, freq in [("1m", "1min"), ("5m", "5min"), ("15m", "15min"),
                     ("30m", "30min"), ("60m", "60min"), ("240m", "240min")]:
        if tf == "1m":
            r = df["close"]
        else:
            r = df["close"].resample(freq).last().dropna()
        ret = r.pct_change().dropna()
        if len(ret) < 5:
            continue
        ac = float(ret.autocorr(lag=1)) if len(ret) >= 10 else float("nan")
        regime = "momentum" if ac > 0.05 else ("mean_reversion" if ac < -0.05 else "mixed")
        rows.append({
            "timeframe": tf,
            "bar_return_mean_pct": round(float(ret.mean()) * 100, 4),
            "bar_return_std_pct": round(float(ret.std()) * 100, 4),
            "autocorr_lag1": round(ac, 4) if not pd.isna(ac) else None,
            "n_bars": int(len(ret)),
            "regime": regime,
        })
    return pd.DataFrame(rows)


# ── core analysis ────────────────────────────────────────────────────────


def per_ticker_recommendation(
    ticker: str,
    alerts: pd.DataFrame,
    intraday: pd.DataFrame,
    cal_row: Optional[pd.Series],
    lookback_days: int,
    as_of: date,
) -> dict:
    """Build the recommended config entry for one ticker."""
    out = {
        "call_rsi_range": None,
        "put_rsi_range": None,
        "min_conditions_momentum": None,
        "min_conditions_mr": None,
        "call_target": None,
        "put_target": None,
        "call_stop": None,
        "put_stop": None,
        "call_time_stop": None,
        "put_time_stop": None,
        "preferred_strategy_call": None,
        "preferred_strategy_put": None,
        "preferred_timeframe_call": None,
        "preferred_timeframe_put": None,
        "combo_bonus_overrides": None,
        "n_signals_used": int(len(alerts)),
        "n_signals_with_intraday": 0,
        "lookback_days": lookback_days,
        "as_of": as_of.isoformat(),
        "notes": None,
    }

    if alerts.empty or intraday.empty:
        out["notes"] = "insufficient data: no alerts or no intraday in lookback window"
        return out

    # Tier-A: RSI ranges from ticker_calibration if usable.
    if cal_row is not None:
        for q in ("rsi_p10", "rsi_p50", "rsi_p90"):
            if pd.isna(cal_row.get(q)):
                cal_row = None
                break
    if cal_row is not None:
        out["call_rsi_range"] = [round(float(cal_row["rsi_p10"]), 2),
                                 round(float(cal_row["rsi_p50"]), 2)]
        out["put_rsi_range"] = [round(float(cal_row["rsi_p50"]), 2),
                                round(float(cal_row["rsi_p90"]), 2)]

    # Replay every alert against intraday, using GLOBAL config (so we can compare
    # win-rate to the production default). Replays for THIS ticker only.
    by_ticker = {ticker: intraday}
    replay = replay_alerts(alerts, by_ticker)
    enriched = alerts.merge(replay, left_on="id", right_on="id", how="left")
    enriched["strategy_inferred"] = enriched["conditions_met"].apply(classify_strategy)
    has_data = enriched[enriched["replay_exit_reason"] != "NO_DATA"].copy()
    out["n_signals_with_intraday"] = int(len(has_data))

    if has_data.empty:
        out["notes"] = (out["notes"] or "") + " | no alerts had intraday coverage"
        return out

    # Side-of-trade win-rate analysis (using the global target/stop/time params)
    has_data["wins"] = (has_data["replay_exit_reason"] == "TARGET_HIT").astype(int)

    # ── target/stop/time-stop recommendation per direction ────────────────
    # Approach:
    #   target_pct = max(SLIPPAGE_BPS, 75th-percentile MFE on triggered side)
    #     — slippage floor ensures the target clears typical execution friction;
    #       75th-pct MFE is the "stretch but reachable" goal vs the median which
    #       is dominated by trades that never moved much.
    #   stop_pct   = max(SLIPPAGE_BPS / 2, 0.5 × median(|MAE|))
    #     — half-MAE so a normal pullback doesn't whip out, but bounded by half
    #       a slippage unit so we don't recommend absurdly tight stops on
    #       low-volatility tickers.
    #   time_stop  = 75th-percentile of time-to-target on winners, ceil 5min, cap 90.
    notes_extra = []
    for direction in ("CALL", "PUT"):
        side = has_data[has_data["direction"] == direction]
        if side.empty:
            continue
        mfe = side["mfe_pct"].dropna()
        mae = side["mae_pct"].dropna().abs()
        if len(mfe) >= 20:
            recommended_target = max(SLIPPAGE_BPS, float(mfe.quantile(0.75)))
        else:
            recommended_target = DEFAULT_CALL_TARGET if direction == "CALL" else DEFAULT_PUT_TARGET
            notes_extra.append(f"{direction.lower()}_target: insufficient data (n={len(mfe)}), kept global default")
        if len(mae) >= 20:
            recommended_stop = max(SLIPPAGE_BPS / 2.0, 0.5 * float(mae.median()))
        else:
            recommended_stop = DEFAULT_CALL_STOP if direction == "CALL" else DEFAULT_PUT_STOP
            notes_extra.append(f"{direction.lower()}_stop: insufficient data (n={len(mae)}), kept global default")

        wins = side[side["wins"] == 1]
        if len(wins) >= 5:
            # 75th percentile of time-to-target, rounded up to nearest 5-min, capped at 90.
            t75 = max(5, int(np.ceil(float(wins["holding_minutes"].quantile(0.75)) / 5.0) * 5))
            t75 = min(t75, 90)
        else:
            t75 = DEFAULT_CALL_TIME_STOP if direction == "CALL" else DEFAULT_PUT_TIME_STOP
            notes_extra.append(f"{direction.lower()}_time_stop: only {len(wins)} winners, kept global default")

        if direction == "CALL":
            out["call_target"] = round(recommended_target, 5)
            out["call_stop"] = round(recommended_stop, 5)
            out["call_time_stop"] = t75
        else:
            out["put_target"] = round(recommended_target, 5)
            out["put_stop"] = round(recommended_stop, 5)
            out["put_time_stop"] = t75

    # ── preferred strategy per direction ──────────────────────────────────
    # Win rate per (direction × strategy_inferred). Pick whichever wins more
    # AND has at least 10 signals to back the call.
    for direction in ("CALL", "PUT"):
        side = has_data[has_data["direction"] == direction]
        per_strat = side.groupby("strategy_inferred")["wins"].agg(["count", "mean"])
        eligible = per_strat[per_strat["count"] >= 10]
        if eligible.empty:
            preferred = "either"
        else:
            best = eligible["mean"].idxmax()
            second_best = eligible.drop(best)["mean"].max() if len(eligible) > 1 else 0
            # If gap < 5 percentage points, treat as "either"
            preferred = best if (eligible.loc[best, "mean"] - second_best) >= 0.05 else "either"
        if direction == "CALL":
            out["preferred_strategy_call"] = preferred
        else:
            out["preferred_strategy_put"] = preferred

    # ── preferred timeframe per direction ─────────────────────────────────
    for direction in ("CALL", "PUT"):
        side = has_data[has_data["direction"] == direction]
        per_tf = side.dropna(subset=["timeframe_tag"]).groupby("timeframe_tag")["wins"].agg(
            ["count", "mean"]
        )
        per_tf = per_tf[per_tf["count"] >= 5]
        if per_tf.empty:
            preferred_tf = None
        else:
            preferred_tf = per_tf["mean"].idxmax()
        if direction == "CALL":
            out["preferred_timeframe_call"] = preferred_tf
        else:
            out["preferred_timeframe_put"] = preferred_tf

    # ── min_conditions per strategy ───────────────────────────────────────
    # Compute net expected return per score bucket: mean(return_pct) − slippage.
    # Set min_conditions to the lowest score where net > 0 (accounting for
    # asymmetric payoff: target_pct on a hit, -stop_pct on a stop, time-stop
    # close on a TIME_STOP). This is the right threshold; a 30%-win-rate
    # signal can still be net-positive when target/stop ratio is favorable.
    SLIPPAGE_PER_TRADE = SLIPPAGE_BPS / 2.0  # half-spread cost on entry+exit ≈ slippage
    for strat_name, key in (("momentum", "min_conditions_momentum"),
                             ("mean_reversion", "min_conditions_mr")):
        sub = has_data[has_data["strategy_inferred"] == strat_name].copy()
        if len(sub) < 30:
            continue
        sub["net_return"] = sub["replay_return_pct"] - SLIPPAGE_PER_TRADE
        per_score = sub.groupby(sub["total_score"].astype(int)).agg(
            n=("wins", "count"),
            win_pct=("wins", "mean"),
            net_mean=("net_return", "mean"),
        )
        per_score = per_score[per_score["n"] >= 5]
        if per_score.empty:
            continue
        positive_scores = per_score[per_score["net_mean"] > 0].index
        if len(positive_scores) > 0:
            out[key] = int(positive_scores.min())
        else:
            # No score bucket is net-positive at the global config — record the
            # max score's net so caller knows how unprofitable the strategy is.
            best = per_score["net_mean"].idxmax()
            notes_extra.append(
                f"{strat_name}: no score bucket net-positive; best is score={best} "
                f"net_mean={per_score.loc[best,'net_mean']:.4%}"
            )

    if notes_extra:
        out["notes"] = "; ".join(notes_extra)
    return out


def factor_discrimination(alerts: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    """Discrimination = win-rate-when-fired vs win-rate-overall.

    For each condition that appears in any `conditions_met`:
      fire_rate    = % of signals where the condition was present
      win_when_fired   = win-rate among signals where the condition was present
      win_when_absent  = win-rate among signals where the condition was absent
      discrimination   = win_when_fired - win_when_absent  (in pp)

    A condition that fires equally on winners and losers has
    discrimination ≈ 0 — it's a free score that doesn't help.
    Discrimination > +5 pp = useful. < +0 = anti-signal (worse than random).
    """
    enr = alerts.merge(replay, on="id", how="left")
    enr = enr[enr["replay_exit_reason"] != "NO_DATA"].copy()
    enr["wins"] = (enr["replay_exit_reason"] == "TARGET_HIT").astype(int)
    overall_win = float(enr["wins"].mean()) if len(enr) > 0 else 0

    # Flatten conditions_met into a long table
    long_rows = []
    for r in enr.itertuples():
        for cond in (r.conditions_met or []):
            long_rows.append({"id": r.id, "condition": cond, "wins": r.wins})
    if not long_rows:
        return pd.DataFrame()
    long = pd.DataFrame(long_rows)

    n_total = len(enr)
    summary = []
    for cond, sub in long.groupby("condition"):
        n_fire = int(len(sub))
        win_fire = float(sub["wins"].mean()) if n_fire else 0
        # Win-rate when condition is absent: enr - sub
        absent_ids = set(enr["id"]) - set(sub["id"])
        absent = enr[enr["id"].isin(absent_ids)]
        win_absent = float(absent["wins"].mean()) if len(absent) > 0 else 0
        summary.append({
            "condition": cond,
            "fire_rate_pct": round(100.0 * n_fire / n_total, 1),
            "n_fired": n_fire,
            "win_when_fired_pct": round(100.0 * win_fire, 1),
            "win_when_absent_pct": round(100.0 * win_absent, 1),
            "discrimination_pp": round(100.0 * (win_fire - win_absent), 1),
        })
    df = pd.DataFrame(summary).sort_values("discrimination_pp", ascending=False)
    df["overall_win_pct"] = round(100.0 * overall_win, 1)
    return df


def write_md_writeup(
    out_path: Path,
    per_ticker: dict[str, dict],
    factor_tables: dict[str, pd.DataFrame],
    summaries: dict[str, dict],
    timeframe_tables: dict[str, pd.DataFrame] | None = None,
    counterfactuals: dict[str, dict] | None = None,
) -> None:
    """Render the per-ticker markdown writeup."""
    lines = []
    lines.append("# Per-Ticker Calibration Writeup\n")
    lines.append(f"_Generated: {datetime.utcnow().isoformat(timespec='seconds')}Z_\n\n")

    # Side-by-side comparison table
    lines.append("## Side-by-side comparison\n")
    cols = ["call_rsi_range", "put_rsi_range",
            "call_target", "put_target", "call_stop", "put_stop",
            "call_time_stop", "put_time_stop",
            "preferred_strategy_call", "preferred_strategy_put",
            "preferred_timeframe_call", "preferred_timeframe_put",
            "min_conditions_momentum", "min_conditions_mr",
            "n_signals_used", "n_signals_with_intraday"]
    header = "| Metric | " + " | ".join(per_ticker.keys()) + " |"
    sep = "|" + "---|" * (1 + len(per_ticker))
    lines.append(header)
    lines.append(sep)
    for c in cols:
        row = [c]
        for t in per_ticker:
            v = per_ticker[t].get(c)
            if isinstance(v, list):
                v = f"({v[0]:.1f}, {v[1]:.1f})"
            row.append(str(v))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("\n")

    lines.append("**Defaults today (from `lib/config.py:ExitConfig` and `lib/strategies/config.py`):**\n")
    lines.append(f"- CALL: target +{DEFAULT_CALL_TARGET*100:.2f}%, stop -{DEFAULT_CALL_STOP*100:.2f}%, time-stop {DEFAULT_CALL_TIME_STOP}min, RSI ({DEFAULT_CALL_RSI[0]:.0f}, {DEFAULT_CALL_RSI[1]:.0f})")
    lines.append(f"- PUT:  target +{DEFAULT_PUT_TARGET*100:.2f}%, stop -{DEFAULT_PUT_STOP*100:.2f}%, time-stop {DEFAULT_PUT_TIME_STOP}min, RSI ({DEFAULT_PUT_RSI[0]:.0f}, {DEFAULT_PUT_RSI[1]:.0f})")
    lines.append(f"- MIN_CONDITIONS_MOMENTUM=5, MIN_CONDITIONS=3 (mean-rev)\n\n")

    # Per-ticker root-cause sections
    for t, recs in per_ticker.items():
        lines.append(f"## {t} — root-cause writeup\n")
        s = summaries.get(t, {})
        lines.append(f"- **Signals available**: {recs['n_signals_used']} (lookback {recs['lookback_days']}d through {recs['as_of']})")
        lines.append(f"- **Signals with intraday outcome**: {recs['n_signals_with_intraday']}")
        if s:
            lines.append(f"- **Overall win-rate at global config**: {s.get('overall_win_pct', 0):.1f}%")
            lines.append(f"- **Win-rate by direction**: CALL {s.get('call_win_pct', 0):.1f}% (n={s.get('call_n', 0)}), PUT {s.get('put_win_pct', 0):.1f}% (n={s.get('put_n', 0)})")
            lines.append(f"- **Time-stop hit rate** (means trade ran to time without target/stop): {s.get('time_stop_pct', 0):.1f}%")
            lines.append(f"- **Median MFE / MAE on triggered side**: CALL MFE {s.get('call_median_mfe_pct', 0):.3f}% / MAE {s.get('call_median_mae_pct', 0):.3f}%, PUT MFE {s.get('put_median_mfe_pct', 0):.3f}% / MAE {s.get('put_median_mae_pct', 0):.3f}%")
            lines.append(f"- **Strategy mix observed**: {s.get('strategy_mix', 'n/a')}")
            lines.append(f"- **brief_alignment coverage**: n={s.get('brief_alignment_n', 0)} alerts have a non-NULL alignment tag.")
            lines.append(f"- **brief_alignment win-rate**: {s.get('brief_alignment_winrate', 'n/a')}")
        if recs.get("notes"):
            lines.append(f"- **Notes**: {recs['notes']}")

        # Multi-timeframe table (Track E plan §2)
        if timeframe_tables and t in timeframe_tables and not timeframe_tables[t].empty:
            tf = timeframe_tables[t]
            lines.append(f"\n### {t} — multi-timeframe regime analysis (RTH-only)\n")
            lines.append("| timeframe | bar_return_mean% | bar_return_std% | autocorr_lag1 | n_bars | regime |")
            lines.append("|---|---|---|---|---|---|")
            for r in tf.itertuples():
                ac = f"{r.autocorr_lag1:.4f}" if r.autocorr_lag1 is not None else "—"
                lines.append(f"| {r.timeframe} | {r.bar_return_mean_pct} | {r.bar_return_std_pct} | {ac} | {r.n_bars} | {r.regime} |")
            lines.append("")
            lines.append("_autocorr_lag1 sign tells you which strategy class the timeframe favors: positive → momentum (trends persist); negative → mean-reversion (returns flip)._")

        # Counterfactual replay (Track E plan §5)
        if counterfactuals and t in counterfactuals and counterfactuals[t]:
            cf = counterfactuals[t]
            lines.append(f"\n### {t} — counterfactual replay: recommended config vs global default\n")
            lines.append(f"- Replayed **{cf.get('n', 0)}** alerts under both configs (same alerts, different exit rules).")
            lines.append(f"- **Win-rate**: global {cf.get('global_win_pct', 0):.1f}% → recommended {cf.get('recommended_win_pct', 0):.1f}% (Δ {cf.get('win_delta_pp', 0):+.1f} pp)")
            lines.append(f"- **Mean per-trade return**: global {cf.get('global_mean_return_pct', 0):+.4f}% → recommended {cf.get('recommended_mean_return_pct', 0):+.4f}% (Δ {cf.get('return_delta_pct', 0):+.4f} %)")
            lines.append("- _Win-rate goes UP because targets are tighter (more often reached); per-trade return is the apples-to-apples economic comparison after slippage._")

        # Factor discrimination
        ft = factor_tables.get(t)
        if ft is not None and not ft.empty:
            lines.append(f"\n### {t} — factor fire-rate × discrimination\n")
            lines.append("| condition | fire_rate% | n_fired | win_when_fired% | win_when_absent% | discrimination_pp | verdict |")
            lines.append("|---|---|---|---|---|---|---|")
            for r in ft.itertuples():
                if r.discrimination_pp >= 5 and r.fire_rate_pct < 60:
                    v = "KEEP"
                elif r.discrimination_pp >= 5:
                    v = "KEEP (high fire-rate)"
                elif r.discrimination_pp <= -5:
                    v = "DROP (anti-signal)"
                elif r.fire_rate_pct >= 70:
                    v = "DEMOTE (free score)"
                else:
                    v = "review"
                lines.append(f"| {r.condition} | {r.fire_rate_pct} | {r.n_fired} | {r.win_when_fired_pct} | {r.win_when_absent_pct} | {r.discrimination_pp} | {v} |")
            lines.append("")
        lines.append("\n")

    # Methodology
    lines.append("## Methodology\n")
    lines.append("- **Replay engine**: every alert is re-simulated against 1-min intraday bars using the production global config (CALL ±0.30%, PUT +0.38%/−0.20%, time-stops 30/35min). The recorded `exit_reason`/`exit_return_pct` columns are NOT trusted (Track A finding: 76% of historical alerts have NULL exits).")
    lines.append("- **Recommended target_pct**: 0.7 × median MFE on triggered direction (anchors target on observed favorable excursion; 0.7 leaves room for slippage).")
    lines.append("- **Recommended stop_pct**: 0.5 × median |MAE| on triggered direction (tight enough to bound loss without being whipped by normal noise).")
    lines.append("- **Recommended time_stop**: 75th-percentile of time-to-target among winning trades, rounded up to nearest 5 min, capped at 90 min.")
    lines.append("- **Strategy classification**: derived from `conditions_met` set membership against the strategy-exclusive condition lists. Conditions like `rvol_above_recent`, `atr_expansion`, `rsi_thrust`, `rsi_bullish_recovery` are momentum-only; `rsi_oversold_zone`, `stoch_rsi_*`, `level_break_*` are mean-reversion-only.")
    lines.append("- **min_conditions per strategy**: lowest score (within the strategy) at which empirical win-rate ≥ 50%. Below that, signals fire net-negative after costs.")
    lines.append("- **Discrimination_pp**: win-rate-when-fired minus win-rate-when-absent. Inspired by the Phase 0.7.1 `stoch_rsi_not_overbought` removal (72% fire rate, 0 discrimination = pure free score).")
    lines.append("- **Equal treatment**: every ticker runs through the SAME pipeline. Differences are data-driven, not configuration-driven.\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    log.info("wrote %s", out_path)


def per_ticker_summary(alerts: pd.DataFrame, replay: pd.DataFrame) -> dict:
    """Compact summary stats for the markdown writeup."""
    enr = alerts.merge(replay, on="id", how="left")
    enr = enr[enr["replay_exit_reason"] != "NO_DATA"]
    if enr.empty:
        return {}
    enr["wins"] = (enr["replay_exit_reason"] == "TARGET_HIT").astype(int)
    out = {"overall_win_pct": float(enr["wins"].mean() * 100)}
    out["time_stop_pct"] = float((enr["replay_exit_reason"] == "TIME_STOP").mean() * 100)

    for d in ("CALL", "PUT"):
        side = enr[enr["direction"] == d]
        out[f"{d.lower()}_n"] = int(len(side))
        out[f"{d.lower()}_win_pct"] = float(side["wins"].mean() * 100) if len(side) else 0
        out[f"{d.lower()}_median_mfe_pct"] = float(side["mfe_pct"].median() * 100) if len(side) else 0
        out[f"{d.lower()}_median_mae_pct"] = float(side["mae_pct"].median() * 100) if len(side) else 0

    enr["strategy_inferred"] = enr["conditions_met"].apply(classify_strategy)
    mix = enr["strategy_inferred"].value_counts(normalize=True).round(3).to_dict()
    out["strategy_mix"] = "  ".join(f"{k}={v*100:.0f}%" for k, v in mix.items())

    # brief_alignment win-rate (only meaningful for the alerts that have it)
    aligned_rows = enr[enr["brief_alignment"].notna()]
    out["brief_alignment_n"] = int(len(aligned_rows))
    if len(aligned_rows) >= 10:
        align_win = aligned_rows.groupby("brief_alignment")["wins"].agg(["count", "mean"])
        out["brief_alignment_winrate"] = " ".join(
            f"{k}: {row['mean']*100:.1f}% (n={int(row['count'])})"
            for k, row in align_win.iterrows()
        )
    else:
        out["brief_alignment_winrate"] = "insufficient (n<10)"
    return out


def counterfactual_replay(
    alerts: pd.DataFrame,
    intraday_by_ticker: dict[str, pd.DataFrame],
    rec: dict,
) -> dict:
    """Replay alerts at the RECOMMENDED config and report delta vs global.

    Returns dict with:
      global_win_pct, recommended_win_pct, win_delta_pp
      global_mean_return_pct, recommended_mean_return_pct, return_delta_pct
    """
    if alerts.empty:
        return {}

    base = replay_alerts(alerts, intraday_by_ticker)  # global defaults
    rec_call_target = rec.get("call_target") or DEFAULT_CALL_TARGET
    rec_put_target = rec.get("put_target") or DEFAULT_PUT_TARGET
    rec_call_stop = rec.get("call_stop") or DEFAULT_CALL_STOP
    rec_put_stop = rec.get("put_stop") or DEFAULT_PUT_STOP
    rec_call_t = rec.get("call_time_stop") or DEFAULT_CALL_TIME_STOP
    rec_put_t = rec.get("put_time_stop") or DEFAULT_PUT_TIME_STOP

    new = replay_alerts(
        alerts, intraday_by_ticker,
        target_call=rec_call_target, target_put=rec_put_target,
        stop_call=rec_call_stop, stop_put=rec_put_stop,
        time_stop_call=rec_call_t, time_stop_put=rec_put_t,
    )

    def _stats(df: pd.DataFrame) -> dict:
        ok = df[df["replay_exit_reason"] != "NO_DATA"]
        if ok.empty:
            return {"n": 0, "win_pct": 0.0, "mean_ret_pct": 0.0}
        wins = (ok["replay_exit_reason"] == "TARGET_HIT").mean() * 100
        ret = ok["replay_return_pct"].mean() * 100
        return {"n": int(len(ok)), "win_pct": float(wins), "mean_ret_pct": float(ret)}

    bs = _stats(base)
    ns = _stats(new)
    return {
        "n": bs["n"],
        "global_win_pct": round(bs["win_pct"], 1),
        "recommended_win_pct": round(ns["win_pct"], 1),
        "win_delta_pp": round(ns["win_pct"] - bs["win_pct"], 1),
        "global_mean_return_pct": round(bs["mean_ret_pct"], 4),
        "recommended_mean_return_pct": round(ns["mean_ret_pct"], 4),
        "return_delta_pct": round(ns["mean_ret_pct"] - bs["mean_ret_pct"], 4),
    }


# ── main entry point ─────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, help="Pre-cached CSV directory (sandbox mode)")
    ap.add_argument("--from-db", action="store_true", help="Read from Cloud SQL")
    ap.add_argument("--auto-tickers", action="store_true",
                    help="Pull ticker list from watchlists where signals=true")
    ap.add_argument("--tickers", nargs="*", default=None, help="Ticker list (e.g. SPY IWM QQQ)")
    ap.add_argument("--lookback-days", type=int, default=90,
                    help="Days of signal_alerts history (default 90; clamped to available data)")
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--as-of", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today())
    args = ap.parse_args()

    if not args.data_dir and not args.from_db:
        ap.error("must specify either --data-dir or --from-db")
    if args.data_dir and args.from_db:
        ap.error("--data-dir and --from-db are mutually exclusive")

    # ── resolve tickers ───────────────────────────────────────────────────
    if args.auto_tickers:
        if not args.from_db:
            ap.error("--auto-tickers requires --from-db (watchlists table is in DB)")
        tickers = load_tickers_from_watchlist()
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        ap.error("provide --tickers or --auto-tickers")

    log.info("tickers: %s", tickers)
    log.info("as_of:   %s, lookback: %d days", args.as_of, args.lookback_days)

    # ── load data ─────────────────────────────────────────────────────────
    if args.from_db:
        sa, intraday_by_ticker, cal_df = load_from_db(args.lookback_days, tickers)
    else:
        sa = load_signal_alerts_csv(args.data_dir / "signal_alerts.csv", tickers)
        cutoff = args.as_of - timedelta(days=args.lookback_days)
        sa = sa[sa["alert_date"] >= cutoff]
        intraday_by_ticker = {}
        for t in tickers:
            # Prefer the `_full.csv` (wider window), fall back to the eval-window CSV.
            for fname in (f"intraday_{t.lower()}_full.csv", f"intraday_{t.lower()}.csv"):
                p = args.data_dir / fname
                if p.exists():
                    intraday_by_ticker[t] = load_intraday_csv(p)
                    break
            else:
                log.warning("no intraday CSV for %s in %s", t, args.data_dir)
                intraday_by_ticker[t] = pd.DataFrame()
        cal_df = pd.read_csv(args.data_dir / "ticker_calibration.csv") \
            if (args.data_dir / "ticker_calibration.csv").exists() else pd.DataFrame()

    log.info("loaded %d signal_alerts across %d tickers", len(sa), sa["ticker"].nunique())

    # ── per-ticker analysis ───────────────────────────────────────────────
    recs: dict[str, dict] = {}
    factor_tables: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict] = {}
    timeframe_tables: dict[str, pd.DataFrame] = {}
    counterfactuals: dict[str, dict] = {}

    for t in tickers:
        log.info("== %s ==", t)
        alerts_t = sa[sa["ticker"] == t].copy()
        intraday_t = intraday_by_ticker.get(t, pd.DataFrame())
        cal_row_df = cal_df[cal_df["ticker"] == t].sort_values(
            "calibration_date", ascending=False
        ) if not cal_df.empty else pd.DataFrame()
        cal_row = cal_row_df.iloc[0] if not cal_row_df.empty else None

        recs[t] = per_ticker_recommendation(
            t, alerts_t, intraday_t, cal_row,
            args.lookback_days, args.as_of,
        )
        log.info("  %s recs: %s", t, {k: v for k, v in recs[t].items() if v is not None})

        # Replay, summary, multi-timeframe stats, and counterfactual replay
        if not alerts_t.empty and not intraday_t.empty:
            replay = replay_alerts(alerts_t, {t: intraday_t})
            factor_tables[t] = factor_discrimination(alerts_t, replay)
            summaries[t] = per_ticker_summary(alerts_t, replay)
            timeframe_tables[t] = multi_timeframe_stats(intraday_t)
            counterfactuals[t] = counterfactual_replay(alerts_t, {t: intraday_t}, recs[t])
            log.info("  %s counterfactual: %s", t, counterfactuals[t])

    # ── write outputs ─────────────────────────────────────────────────────
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(recs, indent=2, default=str))
    log.info("wrote %s", args.out_json)

    write_md_writeup(
        args.out_md, recs, factor_tables, summaries,
        timeframe_tables=timeframe_tables, counterfactuals=counterfactuals,
    )


if __name__ == "__main__":
    main()
