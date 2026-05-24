"""End-of-day resolver for brief-playbook outcomes.

For each row in premarket_analysis (analysis_date, ticker), walks the
day's market_data_intraday bars and computes:

  - When (if at all) the recommended CALL/PUT trigger was reached
  - When each of T1 / T2 / T3 was reached
  - When the stop was hit
  - Whether there was a reversal (price triggered, then went to stop)
  - Time-to-target-1 in minutes
  - MAE (max adverse excursion) and MFE (max favorable excursion) %
  - Realized EOD pnl % (priority: stop_hit | target_hit | EOD_close)
  - EOD pnl in $ (assuming $10,000 notional)

Idempotent: re-running on the same date overwrites with the same values.

Cron: ``30 16 * * 1-5`` America/New_York (16:30 ET, after RTH close).

Environment overrides:
  - PLAYBOOK_RESOLVE_DATE=YYYY-MM-DD : resolve a specific date instead of
    yesterday/today (for backfill or manual one-off).
  - PLAYBOOK_RESOLVE_TICKERS=SPY,QQQ : resolve only these tickers.
  - PLAYBOOK_RESOLVE_NOTIONAL=10000 : dollar notional for the $-pnl calc.
  - PLAYBOOK_RESOLVE_FORCE=true : re-resolve even if outcome_resolved_at
    is already set (default: skip).

Usage:
  # Daily cron (today's row, all tickers):
  python -m gcp.premarket_playbook_resolver

  # Backfill the 5/4-5/8 audit window:
  for d in 2026-05-04 2026-05-05 2026-05-06 2026-05-07 2026-05-08; do
    PLAYBOOK_RESOLVE_DATE=$d python -m gcp.premarket_playbook_resolver
  done

  # Force re-resolve one ticker on one date:
  PLAYBOOK_RESOLVE_DATE=2026-05-06 PLAYBOOK_RESOLVE_TICKERS=QQQ \
    PLAYBOOK_RESOLVE_FORCE=true python -m gcp.premarket_playbook_resolver
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Resolver version stamped on every row — bump when the math changes so
# callers can detect "this row was resolved by an older version, re-run."
RESOLVER_VERSION = '2026-05-11.v1'

# Default notional for $-pnl computation. Per-ticker overrides via env
# var; future enhancement could read from a config table.
DEFAULT_NOTIONAL = 10_000.0


@dataclass
class LegOutcome:
    """Resolved outcome for one CALL or PUT leg."""
    trigger_hit_ts: Optional[datetime] = None
    t1_hit_ts: Optional[datetime] = None
    t2_hit_ts: Optional[datetime] = None
    t3_hit_ts: Optional[datetime] = None
    stop_hit_ts: Optional[datetime] = None
    reversal_after_trigger: Optional[bool] = None
    time_to_t1_min: Optional[int] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    eod_pnl_pct: Optional[float] = None
    eod_pnl_dollar: Optional[float] = None


def derive_level_map_from_daily(ticker: str, analysis_date: date, engine) -> Optional[dict]:
    """Self-healing fallback: re-derive the structured CALL/PUT setup by
    calling the same ``lib.strat_levels.build_level_map`` the brief writer
    uses, against daily data filtered to dates < ``analysis_date``.

    Returns a dict of structured fields ready to UPSERT into
    premarket_analysis (calls_trigger_price / puts_trigger_price /
    stops / T1-T3 / *_name), or None when daily data is missing.

    This exists because historical premarket_analysis rows (pre-PR shipping
    the structured-column writer) have NULL trigger/stop/target columns.
    Rather than parse the prose ``playbook`` text (fragile + error-prone),
    the resolver re-runs the brief's level-map logic against the same
    daily data the brief would have seen. Same source-of-truth function,
    same answer. CLAUDE.md §3.6 — production replay paths, no throwaway
    harnesses.
    """
    from lib.strat_levels import build_level_map  # local import to keep top-level light

    # Load daily history for this ticker. We want everything up to and
    # NOT including analysis_date so the level map only sees data the
    # brief could have known about premarket.
    daily_sql = text("""
        SELECT date, open, high, low, close, atr_14, strat_candle, strat_combo
        FROM market_data_daily
        WHERE ticker = :t AND date < :d
        ORDER BY date
    """)
    df = pd.read_sql(daily_sql, engine, params={'t': ticker.upper(), 'd': str(analysis_date)})
    if df.empty or len(df) < 2:
        logger.warning("derive_level_map: insufficient daily rows for %s before %s (%d)",
                       ticker, analysis_date, len(df))
        return None

    df['Date'] = pd.to_datetime(df['date'])
    df = df.set_index('Date').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
    })

    last = df.iloc[-1]
    # current_price proxy: the most-recent close BEFORE analysis_date.
    # This is what a live brief running at 8:30 AM would see when no
    # premarket data has come in yet. Deterministic + reproducible.
    current_price = float(last['Close'])
    atr = float(last['atr_14']) if pd.notna(last['atr_14']) else None
    strat_class = str(last.get('strat_candle') or '')
    combo = str(last.get('strat_combo') or '')

    level_map = build_level_map(
        ticker=ticker, daily_df=df, current_price=current_price,
        daily_strat_class=strat_class, combo=combo,
        atr=atr, analysis_date=analysis_date,
    )

    ct = level_map.calls_trigger or {}
    pt = level_map.puts_trigger or {}
    ct_targets = ct.get('targets', []) if ct else []
    pt_targets = pt.get('targets', []) if pt else []
    return {
        'calls_trigger_price': ct.get('trigger_level'),
        'calls_trigger_name':  ct.get('trigger_name'),
        'calls_stop_price':    ct.get('stop'),
        'calls_stop_name':     ct.get('stop_name'),
        'calls_t1_price': ct_targets[0]['price'] if len(ct_targets) >= 1 else None,
        'calls_t2_price': ct_targets[1]['price'] if len(ct_targets) >= 2 else None,
        'calls_t3_price': ct_targets[2]['price'] if len(ct_targets) >= 3 else None,
        'puts_trigger_price': pt.get('trigger_level'),
        'puts_trigger_name':  pt.get('trigger_name'),
        'puts_stop_price':    pt.get('stop'),
        'puts_stop_name':     pt.get('stop_name'),
        'puts_t1_price': pt_targets[0]['price'] if len(pt_targets) >= 1 else None,
        'puts_t2_price': pt_targets[1]['price'] if len(pt_targets) >= 2 else None,
        'puts_t3_price': pt_targets[2]['price'] if len(pt_targets) >= 3 else None,
    }


def resolve_leg(
    direction: str,         # 'call' or 'put'
    trigger_price: Optional[float],
    stop_price: Optional[float],
    target_prices: list[Optional[float]],   # [t1, t2, t3]
    bars: pd.DataFrame,
    notional: float = DEFAULT_NOTIONAL,
) -> LegOutcome:
    """Resolve one leg's outcome by walking RTH bars chronologically.

    bars: DataFrame with columns 'time', 'open', 'high', 'low', 'close',
    sorted ascending by time. RTH only (caller filters).

    Returns a LegOutcome with hit timestamps and pnl. Fields stay None
    when the leg was never triggered or the input prices are missing.
    """
    out = LegOutcome()
    if trigger_price is None or trigger_price <= 0:
        return out
    if bars.empty:
        return out

    is_call = (direction == 'call')
    sign = 1 if is_call else -1
    targets = [t for t in target_prices if t is not None and t > 0]

    # Phase 1: walk for trigger hit
    trigger_idx = None
    for i, bar in bars.iterrows():
        if is_call:
            if bar['high'] >= trigger_price:
                trigger_idx = i
                break
        else:
            if bar['low'] <= trigger_price:
                trigger_idx = i
                break
    if trigger_idx is None:
        # Never triggered — no pnl, no timestamps.
        return out
    out.trigger_hit_ts = bars.loc[trigger_idx, 'time']

    # Phase 2: from trigger onwards, walk for stop / each target / EOD
    after = bars.loc[trigger_idx:].reset_index(drop=True)
    if after.empty:
        return out

    # Tracking: which targets have been hit (by index in `targets`)
    target_hit_ts = [None] * len(targets)
    stop_hit_ts = None

    # MAE/MFE accumulators over the post-trigger window
    if is_call:
        mfe_price = trigger_price  # max high seen after trigger
        mae_price = trigger_price  # min low seen after trigger
    else:
        mfe_price = trigger_price
        mae_price = trigger_price

    for _, bar in after.iterrows():
        # MFE / MAE update (always)
        if is_call:
            if bar['high'] > mfe_price:
                mfe_price = bar['high']
            if bar['low'] < mae_price:
                mae_price = bar['low']
        else:
            if bar['low'] < mfe_price:
                mfe_price = bar['low']
            if bar['high'] > mae_price:
                mae_price = bar['high']

        # Targets — earliest hit timestamp wins (don't overwrite)
        for ti, tp in enumerate(targets):
            if target_hit_ts[ti] is not None:
                continue
            if is_call and bar['high'] >= tp:
                target_hit_ts[ti] = bar['time']
            elif not is_call and bar['low'] <= tp:
                target_hit_ts[ti] = bar['time']

        # Stop — earliest hit timestamp
        if stop_hit_ts is None and stop_price is not None and stop_price > 0:
            if is_call and bar['low'] <= stop_price:
                stop_hit_ts = bar['time']
            elif not is_call and bar['high'] >= stop_price:
                stop_hit_ts = bar['time']

    # Populate target hit timestamps
    if len(targets) >= 1: out.t1_hit_ts = target_hit_ts[0]
    if len(targets) >= 2: out.t2_hit_ts = target_hit_ts[1]
    if len(targets) >= 3: out.t3_hit_ts = target_hit_ts[2]
    out.stop_hit_ts = stop_hit_ts
    out.reversal_after_trigger = bool(stop_hit_ts and stop_hit_ts > out.trigger_hit_ts)

    # Time-to-T1
    if out.t1_hit_ts:
        delta_sec = (out.t1_hit_ts - out.trigger_hit_ts).total_seconds()
        out.time_to_t1_min = int(delta_sec / 60)

    # MAE/MFE in % (always positive distances)
    if is_call:
        out.mfe_pct = round((mfe_price - trigger_price) / trigger_price * 100, 4)
        out.mae_pct = round((trigger_price - mae_price) / trigger_price * 100, 4)
    else:
        out.mfe_pct = round((trigger_price - mfe_price) / trigger_price * 100, 4)
        out.mae_pct = round((mae_price - trigger_price) / trigger_price * 100, 4)

    # Realized EOD pnl: priority is stop / first target / EOD close
    realized_price = None
    if stop_hit_ts and (not out.t1_hit_ts or stop_hit_ts <= out.t1_hit_ts):
        # Stop hit first or before any target
        realized_price = stop_price
    else:
        # Pick the LAST target that was hit (T3 > T2 > T1) since the trade
        # would have walked through them. If none, exit at EOD close.
        for ti in range(len(targets) - 1, -1, -1):
            if target_hit_ts[ti] is not None:
                realized_price = targets[ti]
                break
        if realized_price is None:
            realized_price = float(after.iloc[-1]['close'])  # EOD close

    if realized_price is not None:
        out.eod_pnl_pct = round(
            sign * (realized_price - trigger_price) / trigger_price * 100, 4
        )
        out.eod_pnl_dollar = round(out.eod_pnl_pct / 100.0 * notional, 2)
    return out


def resolve_one(
    analysis_date: date,
    ticker: str,
    engine,
    notional: float = DEFAULT_NOTIONAL,
    force: bool = False,
) -> Optional[dict]:
    """Resolve outcomes for one (analysis_date, ticker). Returns dict of
    UPDATE values, or None if the row was skipped (no setup, no bars, or
    already resolved without --force).
    """
    # Pull the row
    row_sql = text("""
        SELECT
            calls_trigger_price, calls_stop_price,
            calls_t1_price, calls_t2_price, calls_t3_price,
            puts_trigger_price, puts_stop_price,
            puts_t1_price, puts_t2_price, puts_t3_price,
            outcome_resolved_at
        FROM premarket_analysis
        WHERE analysis_date = :d AND ticker = :t
        LIMIT 1
    """)
    row_df = pd.read_sql(row_sql, engine, params={'d': str(analysis_date), 't': ticker.upper()})
    if row_df.empty:
        logger.info("no premarket_analysis row for %s on %s — skipping", ticker, analysis_date)
        return None
    row = row_df.iloc[0]

    if row['outcome_resolved_at'] is not None and pd.notna(row['outcome_resolved_at']) and not force:
        logger.info("%s %s already resolved at %s — skipping (use force=True to re-run)",
                    ticker, analysis_date, row['outcome_resolved_at'])
        return None

    # Self-healing fallback: if structured input columns are NULL (e.g.
    # historical row written before the structured-column persistence
    # PR), re-derive the level map from daily data using the same
    # build_level_map() function the brief writer uses, then UPDATE the
    # structured columns in-place. Same source-of-truth, same answer.
    structured_inputs = None
    if (
        (row['calls_trigger_price'] is None or pd.isna(row['calls_trigger_price']))
        and (row['puts_trigger_price'] is None or pd.isna(row['puts_trigger_price']))
    ):
        logger.info("%s %s structured inputs are NULL — deriving from daily data",
                    ticker, analysis_date)
        structured_inputs = derive_level_map_from_daily(ticker, analysis_date, engine)
        if structured_inputs is None or (
            structured_inputs['calls_trigger_price'] is None
            and structured_inputs['puts_trigger_price'] is None
        ):
            logger.info("%s %s level map yielded no triggers — skipping", ticker, analysis_date)
            return None
        # Make the row dict look as if these came from the DB so the
        # downstream resolve_leg(...) calls work unchanged.
        row = {**row.to_dict(), **structured_inputs}

    # Pull RTH intraday bars (9:30-16:00 ET = 13:30-20:00 UTC during EDT,
    # 14:30-21:00 UTC during EST). Use ET-aware filtering for DST safety.
    bars_sql = text("""
        SELECT ts AS time, open, high, low, close
        FROM market_data_intraday
        WHERE ticker = :t
          AND (ts AT TIME ZONE 'America/New_York')::date = :d
          AND (ts AT TIME ZONE 'America/New_York')::time >= '09:30'
          AND (ts AT TIME ZONE 'America/New_York')::time <  '16:00'
          AND interval = '1min'
        ORDER BY ts
    """)
    bars = pd.read_sql(bars_sql, engine, params={'t': ticker.upper(), 'd': str(analysis_date)})
    if bars.empty:
        logger.warning("no intraday bars for %s on %s — skipping", ticker, analysis_date)
        return None
    bars['time'] = pd.to_datetime(bars['time'], utc=True)

    def _f(v):
        return float(v) if v is not None and pd.notna(v) else None

    calls_out = resolve_leg(
        direction='call',
        trigger_price=_f(row['calls_trigger_price']),
        stop_price=_f(row['calls_stop_price']),
        target_prices=[
            _f(row['calls_t1_price']), _f(row['calls_t2_price']), _f(row['calls_t3_price'])
        ],
        bars=bars,
        notional=notional,
    )
    puts_out = resolve_leg(
        direction='put',
        trigger_price=_f(row['puts_trigger_price']),
        stop_price=_f(row['puts_stop_price']),
        target_prices=[
            _f(row['puts_t1_price']), _f(row['puts_t2_price']), _f(row['puts_t3_price'])
        ],
        bars=bars,
        notional=notional,
    )

    # Build update payload
    updates = {
        'calls_trigger_hit_ts': calls_out.trigger_hit_ts,
        'calls_t1_hit_ts':      calls_out.t1_hit_ts,
        'calls_t2_hit_ts':      calls_out.t2_hit_ts,
        'calls_t3_hit_ts':      calls_out.t3_hit_ts,
        'calls_stop_hit_ts':    calls_out.stop_hit_ts,
        'calls_reversal_after_trigger': calls_out.reversal_after_trigger,
        'calls_time_to_t1_min': calls_out.time_to_t1_min,
        'calls_mae_pct':        calls_out.mae_pct,
        'calls_mfe_pct':        calls_out.mfe_pct,
        'calls_eod_pnl_pct':    calls_out.eod_pnl_pct,
        'calls_eod_pnl_dollar': calls_out.eod_pnl_dollar,
        'puts_trigger_hit_ts':  puts_out.trigger_hit_ts,
        'puts_t1_hit_ts':       puts_out.t1_hit_ts,
        'puts_t2_hit_ts':       puts_out.t2_hit_ts,
        'puts_t3_hit_ts':       puts_out.t3_hit_ts,
        'puts_stop_hit_ts':     puts_out.stop_hit_ts,
        'puts_reversal_after_trigger': puts_out.reversal_after_trigger,
        'puts_time_to_t1_min':  puts_out.time_to_t1_min,
        'puts_mae_pct':         puts_out.mae_pct,
        'puts_mfe_pct':         puts_out.mfe_pct,
        'puts_eod_pnl_pct':     puts_out.eod_pnl_pct,
        'puts_eod_pnl_dollar':  puts_out.eod_pnl_dollar,
        'outcome_resolved_at':  datetime.utcnow(),
        'outcome_resolver_version': RESOLVER_VERSION,
    }

    # If the fallback re-derived structured inputs, write those too so
    # the row becomes self-describing and future resolver runs skip the
    # re-derivation step.
    if structured_inputs is not None:
        updates.update(structured_inputs)

    update_sql_set_clauses = [
        "calls_trigger_hit_ts = :calls_trigger_hit_ts",
        "calls_t1_hit_ts = :calls_t1_hit_ts",
        "calls_t2_hit_ts = :calls_t2_hit_ts",
        "calls_t3_hit_ts = :calls_t3_hit_ts",
        "calls_stop_hit_ts = :calls_stop_hit_ts",
        "calls_reversal_after_trigger = :calls_reversal_after_trigger",
        "calls_time_to_t1_min = :calls_time_to_t1_min",
        "calls_mae_pct = :calls_mae_pct",
        "calls_mfe_pct = :calls_mfe_pct",
        "calls_eod_pnl_pct = :calls_eod_pnl_pct",
        "calls_eod_pnl_dollar = :calls_eod_pnl_dollar",
        "puts_trigger_hit_ts = :puts_trigger_hit_ts",
        "puts_t1_hit_ts = :puts_t1_hit_ts",
        "puts_t2_hit_ts = :puts_t2_hit_ts",
        "puts_t3_hit_ts = :puts_t3_hit_ts",
        "puts_stop_hit_ts = :puts_stop_hit_ts",
        "puts_reversal_after_trigger = :puts_reversal_after_trigger",
        "puts_time_to_t1_min = :puts_time_to_t1_min",
        "puts_mae_pct = :puts_mae_pct",
        "puts_mfe_pct = :puts_mfe_pct",
        "puts_eod_pnl_pct = :puts_eod_pnl_pct",
        "puts_eod_pnl_dollar = :puts_eod_pnl_dollar",
        "outcome_resolved_at = :outcome_resolved_at",
        "outcome_resolver_version = :outcome_resolver_version",
    ]
    if structured_inputs is not None:
        update_sql_set_clauses.extend([
            "calls_trigger_price = :calls_trigger_price",
            "calls_trigger_name = :calls_trigger_name",
            "calls_stop_price = :calls_stop_price",
            "calls_stop_name = :calls_stop_name",
            "calls_t1_price = :calls_t1_price",
            "calls_t2_price = :calls_t2_price",
            "calls_t3_price = :calls_t3_price",
            "puts_trigger_price = :puts_trigger_price",
            "puts_trigger_name = :puts_trigger_name",
            "puts_stop_price = :puts_stop_price",
            "puts_stop_name = :puts_stop_name",
            "puts_t1_price = :puts_t1_price",
            "puts_t2_price = :puts_t2_price",
            "puts_t3_price = :puts_t3_price",
        ])
    update_sql = text(
        "UPDATE premarket_analysis SET " + ", ".join(update_sql_set_clauses)
        + " WHERE analysis_date = :d AND ticker = :t"
    )

    with engine.begin() as conn:
        conn.execute(update_sql, {**updates, 'd': str(analysis_date), 't': ticker.upper()})
    logger.info("resolved %s %s: calls_pnl=%s%% puts_pnl=%s%%",
                ticker, analysis_date,
                calls_out.eod_pnl_pct, puts_out.eod_pnl_pct)
    return updates


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s :: %(message)s',
    )
    from gcp.database import get_engine, is_cloud_sql_configured

    if not is_cloud_sql_configured():
        logger.error("Cloud SQL not configured; set CLOUD_SQL_CONNECTION_NAME etc.")
        return 1

    # Resolve target date: PLAYBOOK_RESOLVE_DATE env or yesterday (per cron)
    raw_date = os.environ.get('PLAYBOOK_RESOLVE_DATE')
    if raw_date:
        target_date = date.fromisoformat(raw_date)
    else:
        # Cron runs at 16:30 ET = 20:30 UTC; resolve TODAY's date in ET
        from zoneinfo import ZoneInfo
        target_date = datetime.now(ZoneInfo('America/New_York')).date()

    raw_tickers = os.environ.get('PLAYBOOK_RESOLVE_TICKERS', '').strip()
    notional = float(os.environ.get('PLAYBOOK_RESOLVE_NOTIONAL', DEFAULT_NOTIONAL))
    force = os.environ.get('PLAYBOOK_RESOLVE_FORCE', '').lower() == 'true'

    engine = get_engine()

    if raw_tickers:
        tickers = [t.strip().upper() for t in raw_tickers.split(',') if t.strip()]
    else:
        # All tickers with a brief row for that date
        df = pd.read_sql(
            text("SELECT DISTINCT ticker FROM premarket_analysis WHERE analysis_date = :d"),
            engine, params={'d': str(target_date)},
        )
        tickers = df['ticker'].tolist()

    logger.info("resolving %s for %d tickers (force=%s notional=$%.0f): %s",
                target_date, len(tickers), force, notional, ', '.join(tickers))

    n_resolved = 0
    n_skipped = 0
    for ticker in tickers:
        try:
            result = resolve_one(target_date, ticker, engine, notional=notional, force=force)
            if result is not None:
                n_resolved += 1
            else:
                n_skipped += 1
        except Exception as exc:
            logger.exception("resolve failed for %s: %s", ticker, exc)
            n_skipped += 1

    logger.info("done: %d resolved, %d skipped", n_resolved, n_skipped)
    return 0


if __name__ == '__main__':
    sys.exit(main())
