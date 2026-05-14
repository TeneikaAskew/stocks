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

Tunable knobs (env vars, defaults match the values locked in Phase 0.5):
    BRIEF_REACTION_LOOKBACK_QUARTERS  — playability + conditional lookback
                                        (default 12, range 4-20 sane)
    BRIEF_CONDITIONAL_GAP_BAND_PCT    — width of similar-gap band, ±X%
                                        (default 2.0, range 1.0-5.0 sane)
    BRIEF_CONDITIONAL_THRESHOLD       — fraction of n that must agree
                                        for a directional read
                                        (default 0.75, range 0.5-0.9 sane)
    BRIEF_CONDITIONAL_MIN_SAMPLE      — minimum n to attempt a directional
                                        read, else 'skip' (default 3)
"""
from __future__ import annotations

import math
import os
from typing import Optional


# ────────────────────────────────────────────────────────────
# Config — env-var overridable. Read once at import; consumers
# pass values explicitly so unit tests don't depend on env state.
# ────────────────────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    """Read a float env var, fall back to default on missing/bad value."""
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# Public defaults — tests + brief import these so the wired-in values
# stay in sync. To override at runtime, set the env vars at process
# start (Cloud Run job env, local shell, etc).
DEFAULT_LOOKBACK_QUARTERS = _env_int('BRIEF_REACTION_LOOKBACK_QUARTERS', 12)
DEFAULT_GAP_BAND_PCT      = _env_float('BRIEF_CONDITIONAL_GAP_BAND_PCT', 2.0)
DEFAULT_CONDITIONAL_THRESHOLD = _env_float('BRIEF_CONDITIONAL_THRESHOLD', 0.75)
DEFAULT_CONDITIONAL_MIN_SAMPLE = _env_int('BRIEF_CONDITIONAL_MIN_SAMPLE', 3)


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


# Plain-English action hints per archetype (locked-in 2026-05-01 — Option A).
# Used by the brief renderer so the morning reader doesn't have to mentally
# translate trader jargon ('fade', 'IV-crush', etc.). Keep these short —
# they appear as the trailing phrase on each playability row.
ARCHETYPE_ACTION_HINT = {
    'bullish_trend': 'bullish gap play',
    'bearish_trend': 'bearish gap play',
    'reversal_play': 'gap reversal play',
    'mixed':         'low conviction',
    'quiet':         'skip',
}


# Quintile boundaries calibrated against the 21,592-prediction backtest
# (scripts/backtest_playability.py, 2026-05-14). Hit rates per quintile:
#   Q1 (<15.7):     34.8%
#   Q2 (15.7-21.2): 42.9%
#   Q3 (21.2-28.2): 46.5%
#   Q4 (28.2-41.9): 51.7%
#   Q5 (>=41.9):    58.9%
# Boundaries are midpoints between adjacent quintile-avg scores so a
# score landing exactly at the average maps to that quintile.
_QUINTILE_BOUNDARIES = (15.7, 21.2, 28.2, 41.9)


def score_quintile(score: Optional[float]) -> Optional[str]:
    """Return Q1-Q5 label for a playability_score, or None.

    Q5 = top quintile (highest historical hit rate). Q1 = bottom.
    See _QUINTILE_BOUNDARIES for thresholds and calibration source.
    """
    if score is None:
        return None
    for i, bound in enumerate(_QUINTILE_BOUNDARIES, start=1):
        if score < bound:
            return f'Q{i}'
    return 'Q5'


# Quintile → English confidence label used by the brief renderer.
# Hit rates from backtest (2026-05-14):
#   Q5 = 🔥 HIGH   (58.9%)  — size up
#   Q4 = ✅ SOLID  (51.7%)  — standard sizing
#   Q3 = 🟡 OK     (46.5%)  — small position only
#   Q2 = ❓ WEAK   (42.9%)  — paper / watch
#   Q1 = 🚫 SKIP   (34.8%)  — below baseline; brief drops these rows
CONFIDENCE_LABELS = {
    'Q5': '\U0001f525 HIGH',   # 🔥
    'Q4': '✅ SOLID',      # ✅
    'Q3': '\U0001f7e1 OK',     # 🟡
    'Q2': '❓ WEAK',       # ❓
    'Q1': '\U0001f6ab SKIP',   # 🚫
}


def confidence_label(score: Optional[float]) -> Optional[str]:
    """Return the brief's English confidence tag (e.g. '🔥 HIGH') for a
    playability_score, or None if the score isn't computable.
    """
    q = score_quintile(score)
    return CONFIDENCE_LABELS.get(q) if q else None
    return 'Q5'


def action_hint_for_archetype(archetype: Optional[str]) -> str:
    """Return the plain-English action hint for an archetype tag.
    Defaults to 'skip' for None / unknown values."""
    return ARCHETYPE_ACTION_HINT.get(archetype or 'quiet', 'skip')


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

def query_reaction_stats(
    tickers: list[str],
    lookback_quarters: Optional[int] = None,
) -> dict:
    """Fetch per-ticker aggregate stats from earnings_reactions over the
    last `lookback_quarters` quarters.

    `lookback_quarters` defaults to DEFAULT_LOOKBACK_QUARTERS (env var
    BRIEF_REACTION_LOOKBACK_QUARTERS, default 12).

    Returns:
        {ticker: {n_q, move_magnitude_pct, directional_bias_pct,
                  dir_consistency, reversal_rate}}
        Tickers without enough data are simply absent from the dict.
    """
    if lookback_quarters is None:
        lookback_quarters = DEFAULT_LOOKBACK_QUARTERS
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
# Phase 1.6 — Post-Event Conditional Reads
#
# After the gap is known (D+1 morning for AMC, D itself for BMO), the
# long-run playability score is too coarse — it averages over all
# directions and magnitudes. The conditional layer answers a narrower
# question: "Of past quarters where this ticker had a similar gap,
# how often did the move hold vs reverse?"
# ────────────────────────────────────────────────────────────


def query_conditional_reactions(
    ticker: str,
    reaction_basis: str,
    actual_gap_pct: float,
    gap_band_pct: Optional[float] = None,
    lookback_quarters: Optional[int] = None,
) -> dict:
    """Return historical reactions for `ticker` filtered to past quarters
    with a similar gap shape (size and direction).

    Filter:
        - Same ticker
        - Same reaction_basis ('AMC' or 'BMO')
        - reaction_gap_pct within ±gap_band_pct of actual_gap_pct
          (preserves direction since the band is signed-around the
          actual value, e.g. for a +4.85% gap with band=2.0 the
          window is [+2.85%, +6.85%])
        - Last `lookback_quarters` reports

    Returns:
        {
          'n':            int,    # number of similar past quarters
          'held':         int,    # direction_consistent_5d == TRUE
          'reversed':     int,    # is_reversal_5d == TRUE
          'unclear':      int,    # tiny moves, NULL flags
          'avg_sustain_5d_pct': float | None,
          'total_for_ticker': int,  # all rows for this ticker × basis
                                    # (regardless of gap band) — lets
                                    # callers distinguish "no data for
                                    # this ticker yet" (=0) from
                                    # "ticker exists but no similar gaps"
                                    # (>0 with n=0).
        }
        Empty dict if Cloud SQL unavailable.
    """
    if reaction_basis not in ('AMC', 'BMO'):
        return {}
    if gap_band_pct is None:
        gap_band_pct = DEFAULT_GAP_BAND_PCT
    if lookback_quarters is None:
        lookback_quarters = DEFAULT_LOOKBACK_QUARTERS
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}

    lo = actual_gap_pct - gap_band_pct
    hi = actual_gap_pct + gap_band_pct
    # Single query computes both the gap-band-filtered stats AND the
    # unfiltered total for the ticker. `total_for_ticker` lets callers
    # distinguish "we have no data for this ticker yet" from "we have
    # data but today's gap is unprecedented."
    sql = """
        WITH ranked AS (
            SELECT
                reaction_gap_pct,
                direction_consistent_5d,
                is_reversal_5d,
                sustain_5d_pct,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY reported_date DESC
                ) AS rn
            FROM earnings_reactions
            WHERE ticker = :ticker
              AND reaction_basis = :basis
              AND reaction_gap_pct IS NOT NULL
        ),
        windowed AS (
            SELECT * FROM ranked WHERE rn <= :lookback
        )
        SELECT
            COUNT(*) FILTER (
                WHERE reaction_gap_pct BETWEEN :lo AND :hi
            )                                                       AS n,
            COUNT(*) FILTER (
                WHERE reaction_gap_pct BETWEEN :lo AND :hi
                  AND direction_consistent_5d IS TRUE
            )                                                       AS held,
            COUNT(*) FILTER (
                WHERE reaction_gap_pct BETWEEN :lo AND :hi
                  AND is_reversal_5d IS TRUE
            )                                                       AS reversed,
            COUNT(*) FILTER (
                WHERE reaction_gap_pct BETWEEN :lo AND :hi
                  AND (direction_consistent_5d IS NULL OR is_reversal_5d IS NULL)
            )                                                       AS unclear,
            AVG(sustain_5d_pct) FILTER (
                WHERE reaction_gap_pct BETWEEN :lo AND :hi
            )                                                       AS avg_sustain_5d_pct,
            COUNT(*)                                                AS total_for_ticker
        FROM windowed
    """
    df = query_to_dataframe(sql, {
        'ticker':  ticker,
        'basis':   reaction_basis,
        'lookback': lookback_quarters,
        'lo': lo,
        'hi': hi,
    })
    if df.empty:
        return {}
    row = df.iloc[0]
    n = int(row['n'])
    total_for_ticker = int(row.get('total_for_ticker', 0) or 0)
    if n == 0:
        return {'n': 0, 'held': 0, 'reversed': 0, 'unclear': 0,
                'avg_sustain_5d_pct': None,
                'total_for_ticker': total_for_ticker}
    return {
        'n':       n,
        'held':    int(row['held']),
        'reversed': int(row['reversed']),
        'unclear': int(row['unclear']),
        'avg_sustain_5d_pct': _to_float(row.get('avg_sustain_5d_pct')),
        'total_for_ticker': total_for_ticker,
    }


def classify_lean(
    conditional_stats: dict,
    actual_gap_pct: Optional[float] = None,
    min_sample: Optional[int] = None,
    threshold: Optional[float] = None,
) -> str:
    """Map conditional historical stats → plain-English lean phrase.

    Returns one of (Phase 1.6 vocabulary, locked in 2026-05-01):
        'bullish gap play'   — ≥75% similar past gaps held, current gap up
        'bearish gap play'   — ≥75% similar past gaps held, current gap down
        'expect reversal'    — ≥75% similar past gaps reversed within 5d
        'low conviction'     — mixed (no clear pattern at the threshold)
        'skip'               — sample too small (n < min_sample)

    Args:
        conditional_stats: dict from query_conditional_reactions
        actual_gap_pct: today's actual gap (positive=up, negative=down).
            Required for distinguishing bullish vs bearish on a "held"
            pattern.
        min_sample: minimum n to attempt a directional read. Below
            this, return 'skip' regardless of the split.
        threshold: fraction of n that must agree for a directional read.
    """
    if min_sample is None:
        min_sample = DEFAULT_CONDITIONAL_MIN_SAMPLE
    if threshold is None:
        threshold = DEFAULT_CONDITIONAL_THRESHOLD
    if not conditional_stats:
        return 'skip'
    n = conditional_stats.get('n', 0)
    if n < min_sample:
        return 'skip'
    held = conditional_stats.get('held', 0)
    reversed_ = conditional_stats.get('reversed', 0)

    if held / n >= threshold:
        if actual_gap_pct is None:
            return 'low conviction'
        if actual_gap_pct > 0:
            return 'bullish gap play'
        if actual_gap_pct < 0:
            return 'bearish gap play'
        return 'low conviction'  # gap == 0
    if reversed_ / n >= threshold:
        return 'expect reversal'
    return 'low conviction'


def conditional_lean_summary(
    ticker: str,
    reaction_basis: str,
    actual_gap_pct: float,
    gap_band_pct: Optional[float] = None,
    lookback_quarters: Optional[int] = None,
) -> dict:
    """Top-level convenience for the brief — runs the query + classifier
    and returns a renderable summary.

    Returns:
        {
          'n':       int,
          'held':    int,
          'reversed': int,
          'lean':    str,      # plain-English phrase
          'sentence': str,     # ready-to-render summary like
                               # "3 of 4 similar past gaps reversed"
                               # or "" when sample too small
        }
    """
    stats = query_conditional_reactions(
        ticker, reaction_basis, actual_gap_pct,
        gap_band_pct=gap_band_pct,
        lookback_quarters=lookback_quarters,
    )
    lean = classify_lean(stats, actual_gap_pct=actual_gap_pct)

    n = stats.get('n', 0)
    held = stats.get('held', 0)
    reversed_ = stats.get('reversed', 0)
    total_for_ticker = stats.get('total_for_ticker', 0)

    # Build the human-readable sentence describing the dominant pattern.
    # n=0 has two distinct meanings — distinguish them so the brief
    # reader knows whether we have data at all for this ticker.
    if n == 0:
        if total_for_ticker == 0:
            # No earnings_reactions rows for this (ticker, basis) yet —
            # the populator hasn't covered it. Different remediation:
            # one-shot backfill vs accept "this gap is unusual."
            sentence = 'no historical data for this ticker yet'
        else:
            # We have data, but today's gap is outside any past gap's
            # ±band range. Could be unprecedented (real signal) or just
            # extreme (treat with caution).
            sentence = (
                f'no historical analog '
                f'(gap outside typical range, {total_for_ticker} past quarters)'
            )
    elif n < 3:
        sentence = f'too few similar past gaps ({n})'
    elif reversed_ >= held:
        sentence = f'{reversed_} of {n} similar past gaps reversed'
    else:
        sentence = f'{held} of {n} similar past gaps held'

    return {
        'n':       n,
        'held':    held,
        'reversed': reversed_,
        'lean':    lean,
        'sentence': sentence,
    }


# ────────────────────────────────────────────────────────────
# Top-level convenience for consumers (the brief)
# ────────────────────────────────────────────────────────────

def enrich_with_playability(
    rows: list[dict],
    lookback_quarters: Optional[int] = None,
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
    if lookback_quarters is None:
        lookback_quarters = DEFAULT_LOOKBACK_QUARTERS
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


# ════════════════════════════════════════════════════════════
# Pre-earnings drift (added 2026-05-14)
#
# Mirrors the post-earnings playability stack but anchored on
# the 5 trading days BEFORE the report. Surfaces tickers that
# consistently run up (pre_bullish_run) or fade (pre_bearish_fade)
# into the print so the brief can suggest CALL/PUT entries 3-5
# days out instead of only on report day.
#
# All four helpers below are direct symmetric analogs:
#   compute_pre_drift_score  ↔ compute_playability_score
#   classify_pre_drift_archetype ↔ classify_archetype
#   query_pre_drift_stats    ↔ query_reaction_stats
#   enrich_with_pre_drift    ↔ enrich_with_playability
# ════════════════════════════════════════════════════════════

# Quintile boundaries for pre-drift score. CALIBRATION NOTE: these are
# placeholders matching the post-earnings playability boundaries. The
# real values will be set by scripts/backtest_pre_drift.py after the
# walk-forward validation completes. Until that backtest runs, keep
# these in sync with _QUINTILE_BOUNDARIES (line 137) — same shape, same
# magnitudes, so the confidence labels render reasonably.
_PRE_DRIFT_QUINTILE_BOUNDARIES = (15.7, 21.2, 28.2, 41.9)


def pre_drift_score_quintile(score: Optional[float]) -> Optional[str]:
    """Q1-Q5 bucket for a pre_drift_score (vs post-earnings score_quintile)."""
    if score is None:
        return None
    for i, bound in enumerate(_PRE_DRIFT_QUINTILE_BOUNDARIES, start=1):
        if score < bound:
            return f'Q{i}'
    return 'Q5'


def pre_drift_confidence_label(score: Optional[float]) -> Optional[str]:
    """Return the brief's English confidence tag (e.g. '🔥 HIGH') for a
    pre_drift_score. Reuses the same CONFIDENCE_LABELS dict as the
    post-earnings score so the reader sees a consistent vocabulary.
    """
    q = pre_drift_score_quintile(score)
    return CONFIDENCE_LABELS.get(q) if q else None


# Action map — what trade to set up based on pre-earnings drift pattern.
# Quiet skipped at the filter layer (drift < 1.5% magnitude).
PRE_DRIFT_ACTION_HINT = {
    'pre_bullish_run':  'CALL into print',
    'pre_bearish_fade': 'PUT into print',
    'pre_choppy':       '',                # no actionable directional play
    'pre_quiet':        'skip',
}


def pre_drift_action_for_archetype(archetype: Optional[str]) -> str:
    """Return the trade-setup label rendered in the pre-drift embed."""
    return PRE_DRIFT_ACTION_HINT.get(archetype or 'pre_quiet', 'skip')


def compute_pre_drift_score(
    drift_magnitude_pct:      Optional[float],
    typical_daily_return_pct: Optional[float],
    pre_dir_consistency:      Optional[float],
    pre_reversal_rate:        Optional[float],
    options_volume:           Optional[float],
) -> Optional[float]:
    """Pre-earnings drift score. SAME FORMULA SHAPE as playability_score
    so the quintile + confidence-label semantics carry over.

    Inputs:
      drift_magnitude_pct  — mean of |drift_5d_pct| over last 12 quarters
      typical_daily_return_pct — same 60-day median |daily return| baseline
      pre_dir_consistency  — fraction of quarters where drift_5d agrees with
                             the *modal* direction (>0 if mostly up runs,
                             <0 if mostly fades)
      pre_reversal_rate    — fraction where pre_drift_reverses_into_gap
                             (sign flips between pre-run and earnings gap)
      options_volume       — current liquidity proxy (same as post-earnings)
    """
    if drift_magnitude_pct is None or typical_daily_return_pct is None:
        return None
    if typical_daily_return_pct <= 0:
        return None
    if pre_dir_consistency is None or pre_reversal_rate is None:
        return None
    if options_volume is None or options_volume <= 0:
        return None

    move_norm = drift_magnitude_pct / typical_daily_return_pct
    confidence = max(pre_dir_consistency, 0.5 + 0.5 * pre_reversal_rate)
    log_liquidity = math.log(options_volume + 1)
    return move_norm * confidence * log_liquidity


def classify_pre_drift_archetype(
    drift_magnitude_pct:    Optional[float],
    directional_drift_pct:  Optional[float],
    pre_dir_consistency:    Optional[float],
    pre_reversal_rate:      Optional[float],
) -> str:
    """Return one of five pre-drift archetype tags.

      pre_bullish_run  — consistent UP into earnings
      pre_bearish_fade — consistent DOWN into earnings
      pre_choppy       — moves but no consistent direction (or reversal-prone)
      pre_quiet        — drift too small to play (< 1.5% avg magnitude)

    Thresholds mirror classify_archetype()'s shape so the two pipelines
    feel consistent — same magnitude floor (1.5%), same consistency
    threshold (0.65), same directional-bias gate (±0.5%).
    """
    if drift_magnitude_pct is None or drift_magnitude_pct < 1.5:
        return 'pre_quiet'
    if pre_dir_consistency is None or pre_reversal_rate is None:
        return 'pre_quiet'

    # Strong reversal pattern → choppy (no directional bet)
    if pre_reversal_rate >= 0.40 and pre_dir_consistency < 0.50:
        return 'pre_choppy'

    # Directional run with bias
    if pre_dir_consistency >= 0.65 and directional_drift_pct is not None:
        if directional_drift_pct > 0.5:
            return 'pre_bullish_run'
        if directional_drift_pct < -0.5:
            return 'pre_bearish_fade'

    return 'pre_choppy'


def query_pre_drift_stats(
    tickers: list[str],
    lookback_quarters: Optional[int] = None,
) -> dict:
    """Fetch per-ticker pre-drift aggregates over the last N quarters.

    Returns: {ticker: {n_q, drift_magnitude_pct, directional_drift_pct,
                       pre_dir_consistency, pre_reversal_rate}}
    Tickers missing pre-drift data (no D-5 close in window) are absent.
    """
    if lookback_quarters is None:
        lookback_quarters = DEFAULT_LOOKBACK_QUARTERS
    if not tickers:
        return {}
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}

    placeholders = ','.join(f"'{t}'" for t in tickers)
    # NOTE: pre_dir_consistency here means "% of quarters drift was positive"
    # — we treat the modal direction as bullish. classify_pre_drift_archetype
    # then uses both consistency AND directional_drift_pct sign to decide
    # bullish_run vs bearish_fade. This matches how dir_consistency works
    # for post-earnings (sign agreement, not absolute direction).
    sql = f"""
        WITH ranked AS (
            SELECT
                ticker,
                drift_5d_pct,
                pre_drift_consistent_5d,
                pre_drift_reverses_into_gap,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY reported_date DESC
                ) AS rn
            FROM earnings_reactions
            WHERE ticker IN ({placeholders})
              AND drift_5d_pct IS NOT NULL
        )
        SELECT
            ticker,
            COUNT(*)                                            AS n_q,
            AVG(ABS(drift_5d_pct))                              AS drift_magnitude_pct,
            AVG(drift_5d_pct)                                   AS directional_drift_pct,
            AVG(CASE WHEN pre_drift_consistent_5d THEN 1.0
                     WHEN pre_drift_consistent_5d IS NULL THEN NULL
                     ELSE 0.0 END)                              AS pre_dir_consistency,
            AVG(CASE WHEN pre_drift_reverses_into_gap THEN 1.0
                     WHEN pre_drift_reverses_into_gap IS NULL THEN NULL
                     ELSE 0.0 END)                              AS pre_reversal_rate
        FROM ranked
        WHERE rn <= {int(lookback_quarters)}
        GROUP BY ticker
    """
    try:
        df = query_to_dataframe(sql)
    except Exception:
        return {}
    if df.empty:
        return {}
    out = {}
    for _, r in df.iterrows():
        out[r['ticker']] = {
            'n_q':                   int(r['n_q']),
            'drift_magnitude_pct':   _to_float(r.get('drift_magnitude_pct')),
            'directional_drift_pct': _to_float(r.get('directional_drift_pct')),
            'pre_dir_consistency':   _to_float(r.get('pre_dir_consistency')),
            'pre_reversal_rate':     _to_float(r.get('pre_reversal_rate')),
        }
    return out


def enrich_with_pre_drift(
    rows: list[dict],
    lookback_quarters: Optional[int] = None,
    daily_return_window: int = 60,
) -> list[dict]:
    """Attach pre_drift_* fields to each row. Mirror of
    enrich_with_playability() — mutates in place AND returns.

    Adds:
      pre_drift_score, pre_drift_archetype, pre_drift_n_q,
      pre_drift_magnitude_pct, pre_drift_directional_pct,
      pre_dir_consistency, pre_reversal_rate

    Rows where stats are missing get score=None, archetype='pre_quiet'.
    """
    if not rows:
        return rows
    if lookback_quarters is None:
        lookback_quarters = DEFAULT_LOOKBACK_QUARTERS
    tickers = sorted({str(r['ticker']) for r in rows if r.get('ticker')})
    stats_map = query_pre_drift_stats(tickers, lookback_quarters)
    daily_map = query_typical_daily_return(tickers, daily_return_window)

    for r in rows:
        ticker = str(r.get('ticker', ''))
        stats = stats_map.get(ticker)
        typical = daily_map.get(ticker)
        opt_vol = r.get('options_volume')

        if stats is None:
            r['pre_drift_score'] = None
            r['pre_drift_archetype'] = 'pre_quiet'
            r['pre_drift_n_q'] = 0
            continue

        r['pre_drift_score'] = compute_pre_drift_score(
            drift_magnitude_pct      = stats.get('drift_magnitude_pct'),
            typical_daily_return_pct = typical,
            pre_dir_consistency      = stats.get('pre_dir_consistency'),
            pre_reversal_rate        = stats.get('pre_reversal_rate'),
            options_volume           = opt_vol,
        )
        r['pre_drift_archetype'] = classify_pre_drift_archetype(
            drift_magnitude_pct   = stats.get('drift_magnitude_pct'),
            directional_drift_pct = stats.get('directional_drift_pct'),
            pre_dir_consistency   = stats.get('pre_dir_consistency'),
            pre_reversal_rate     = stats.get('pre_reversal_rate'),
        )
        r['pre_drift_n_q']              = stats.get('n_q', 0)
        r['pre_drift_magnitude_pct']    = stats.get('drift_magnitude_pct')
        r['pre_drift_directional_pct']  = stats.get('directional_drift_pct')
        r['pre_dir_consistency']        = stats.get('pre_dir_consistency')
        r['pre_reversal_rate']          = stats.get('pre_reversal_rate')
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
