"""Earnings-reaction analytics — playability score + archetype tagging.

Lives in lib/ per CLAUDE.md "lib/ is the shared backend spine" — the
brief, watchlist UI, and any future ML/analytics consumer all read
the same logic from here.

Locked-in formula (Phase 0.5):

    playability_score = move_magnitude_norm
                      × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                      × log(options_volume + 1)

    move_magnitude_norm = move_magnitude / typical_daily_return

    typical_daily_return = median(|daily_return_pct|) over last 60d

Archetype tagging (used by the brief's playbook section):
    bullish_trend  — high dir_consistency, positive directional_bias
    bearish_trend  — high dir_consistency, negative directional_bias
    reversal_play  — high reversal_rate, low dir_consistency
    mixed          — moderate signals on both axes
    quiet          — small move_magnitude or no clear pattern
"""
from __future__ import annotations

import math
from typing import Optional


# ────────────────────────────────────────────────────────────
# Pure-compute layer
# ────────────────────────────────────────────────────────────

def compute_playability_score(
    move_magnitude_pct: Optional[float],
    typical_daily_return_pct: Optional[float],
    dir_consistency: Optional[float],
    reversal_rate: Optional[float],
    options_volume: Optional[float],
) -> Optional[float]:
    """Compute the locked-in playability score. Returns None if any
    required input is missing.

    move_magnitude_pct:
        mean of |reaction_gap_pct| over last N quarters (% units)
    typical_daily_return_pct:
        median |daily_return_pct| over last ~60 trading days (% units).
        Used to normalize the move so quiet stocks that erupt on
        earnings (FDX 0.9% typical / 7.4% earnings) score above
        already-active stocks (AVGO 1.3% typical / 6.5% earnings).
    dir_consistency:
        fraction in [0,1] of quarters where sign(reaction_gap) ==
        sign(sustain_5d).
    reversal_rate:
        fraction in [0,1] of quarters flagged as is_reversal_5d
        (sign flip + magnitude meets threshold).
    options_volume:
        contracts-per-day liquidity. Use the most recent available
        signal — for forward-looking brief use, earnings_calendar's
        upcoming-week options_volume is the right value.
    """
    if move_magnitude_pct is None or typical_daily_return_pct is None:
        return None
    if typical_daily_return_pct <= 0:
        return None
    if dir_consistency is None or reversal_rate is None:
        return None
    if options_volume is None or options_volume <= 0:
        return None

    move_magnitude_norm = move_magnitude_pct / typical_daily_return_pct
    confidence = max(dir_consistency, 0.5 + 0.5 * reversal_rate)
    log_liquidity = math.log(options_volume + 1)
    return move_magnitude_norm * confidence * log_liquidity


def classify_archetype(
    move_magnitude_pct: Optional[float],
    directional_bias_pct: Optional[float],
    dir_consistency: Optional[float],
    reversal_rate: Optional[float],
) -> str:
    """Return a one-of-five archetype tag based on the 12Q profile.

    Thresholds tuned against the 9-ticker case-study set:
        AVGO  -> bullish_trend (dir_cons 0.83, bias +3.24)
        FDX   -> reversal_play (dir_cons 0.33, rev 0.50)
        NVDA  -> mixed         (dir_cons 0.58, mid)
        LLY   -> bullish_trend (dir_cons 0.67, bias +2.15)
        JPM   -> mixed         (dir_cons 0.58)
        WMT   -> bullish_trend (dir_cons 0.67, bias +1.06)
        JNJ   -> mixed         (small magnitude + mid signals)
        PG    -> mixed
        GOOG  -> mixed
    """
    if move_magnitude_pct is None or move_magnitude_pct < 1.5:
        return 'quiet'
    if dir_consistency is None or reversal_rate is None:
        return 'quiet'

    # Strong reversal pattern wins
    if reversal_rate >= 0.40 and dir_consistency < 0.50:
        return 'reversal_play'

    # Strong directional pattern with bias
    if dir_consistency >= 0.65 and directional_bias_pct is not None:
        if directional_bias_pct > 0.5:
            return 'bullish_trend'
        if directional_bias_pct < -0.5:
            return 'bearish_trend'

    return 'mixed'


# ────────────────────────────────────────────────────────────
# DB query helpers
# ────────────────────────────────────────────────────────────

def query_reaction_stats(tickers: list[str], lookback_quarters: int = 12) -> dict:
    """Fetch per-ticker aggregate stats from earnings_reactions over the
    last `lookback_quarters` quarters.

    Returns:
        {ticker: {n_q, move_magnitude_pct, directional_bias_pct,
                  dir_consistency, reversal_rate}}
        Tickers without enough data are simply absent from the dict.
    """
    if not tickers:
        return {}
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}

    placeholders = ','.join(f"'{t}'" for t in tickers)
    sql = f"""
        WITH ranked AS (
            SELECT
                ticker,
                reaction_gap_pct,
                direction_consistent_5d,
                is_reversal_5d,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY reported_date DESC
                ) AS rn
            FROM earnings_reactions
            WHERE ticker IN ({placeholders})
              AND reaction_gap_pct IS NOT NULL
        )
        SELECT
            ticker,
            COUNT(*)                                                 AS n_q,
            AVG(ABS(reaction_gap_pct))                               AS move_magnitude_pct,
            AVG(reaction_gap_pct)                                    AS directional_bias_pct,
            AVG(CASE WHEN direction_consistent_5d THEN 1.0
                     WHEN direction_consistent_5d IS NULL THEN NULL
                     ELSE 0.0 END)                                   AS dir_consistency,
            AVG(CASE WHEN is_reversal_5d THEN 1.0
                     WHEN is_reversal_5d IS NULL THEN NULL
                     ELSE 0.0 END)                                   AS reversal_rate
        FROM ranked
        WHERE rn <= :lookback
        GROUP BY ticker
    """
    df = query_to_dataframe(sql, {'lookback': lookback_quarters})
    if df.empty:
        return {}

    out: dict = {}
    for _, row in df.iterrows():
        out[str(row['ticker'])] = {
            'n_q':                  int(row['n_q']),
            'move_magnitude_pct':   _to_float(row.get('move_magnitude_pct')),
            'directional_bias_pct': _to_float(row.get('directional_bias_pct')),
            'dir_consistency':      _to_float(row.get('dir_consistency')),
            'reversal_rate':        _to_float(row.get('reversal_rate')),
        }
    return out


def query_typical_daily_return(tickers: list[str], window_days: int = 60) -> dict:
    """Median |daily return %| over the last `window_days` trading days
    per ticker. Returns {ticker: pct} (None when insufficient data)."""
    if not tickers:
        return {}
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}

    placeholders = ','.join(f"'{t}'" for t in tickers)
    sql = f"""
        WITH recent AS (
            SELECT ticker, date, close,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY date DESC
                   ) AS rn
              FROM market_data_daily
             WHERE ticker IN ({placeholders})
        ),
        windowed AS (
            SELECT ticker, date, close
              FROM recent WHERE rn <= :window_size
        ),
        pct_changes AS (
            SELECT
                ticker,
                date,
                close,
                LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
              FROM windowed
        )
        SELECT
            ticker,
            -- Use percentile_cont (median) on the absolute returns
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY ABS((close - prev_close) / prev_close * 100)
            ) AS typical_daily_return_pct
          FROM pct_changes
         WHERE prev_close IS NOT NULL AND prev_close > 0
         GROUP BY ticker
    """
    df = query_to_dataframe(sql, {'window_size': window_days + 5})
    if df.empty:
        return {}
    return {
        str(row['ticker']): _to_float(row.get('typical_daily_return_pct'))
        for _, row in df.iterrows()
    }


# ────────────────────────────────────────────────────────────
# Top-level convenience for consumers (the brief)
# ────────────────────────────────────────────────────────────

def enrich_with_playability(
    rows: list[dict],
    lookback_quarters: int = 12,
    daily_return_window: int = 60,
) -> list[dict]:
    """Add 'playability_score' and 'playability_archetype' to each row in `rows`.

    `rows` is a list of dicts with at least:
      - 'ticker'             (str)
      - 'options_volume'     (int|float|None) — current liquidity proxy

    Mutates the dicts in place AND returns them for chainability.
    Rows where stats are unavailable (no earnings_reactions, no
    OHLCV, no options_volume) get score=None, archetype='quiet'.
    """
    if not rows:
        return rows
    tickers = sorted({str(r['ticker']) for r in rows if r.get('ticker')})
    stats_map = query_reaction_stats(tickers, lookback_quarters)
    daily_map = query_typical_daily_return(tickers, daily_return_window)

    for r in rows:
        ticker = str(r.get('ticker', ''))
        stats = stats_map.get(ticker)
        typical = daily_map.get(ticker)
        opt_vol = r.get('options_volume')

        if stats is None:
            r['playability_score'] = None
            r['playability_archetype'] = 'quiet'
            r['playability_n_q'] = 0
            continue

        r['playability_score'] = compute_playability_score(
            move_magnitude_pct       = stats.get('move_magnitude_pct'),
            typical_daily_return_pct = typical,
            dir_consistency          = stats.get('dir_consistency'),
            reversal_rate            = stats.get('reversal_rate'),
            options_volume           = opt_vol,
        )
        r['playability_archetype'] = classify_archetype(
            move_magnitude_pct   = stats.get('move_magnitude_pct'),
            directional_bias_pct = stats.get('directional_bias_pct'),
            dir_consistency      = stats.get('dir_consistency'),
            reversal_rate        = stats.get('reversal_rate'),
        )
        r['playability_n_q'] = stats.get('n_q', 0)
        # Also expose the underlying inputs so the brief can show them
        r['playability_move_mag_pct']    = stats.get('move_magnitude_pct')
        r['playability_dir_bias_pct']    = stats.get('directional_bias_pct')
        r['playability_dir_consistency'] = stats.get('dir_consistency')
        r['playability_reversal_rate']   = stats.get('reversal_rate')
        r['playability_typical_daily']   = typical
    return rows


# ────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────

def _to_float(v) -> Optional[float]:
    """Normalize numeric DB values (numpy floats, Decimals, None, NaN) to
    Python float | None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f
