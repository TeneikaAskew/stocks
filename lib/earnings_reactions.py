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

import logging
import math
import os
from functools import lru_cache
from typing import Optional

log = logging.getLogger(__name__)


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
# Min past quarters before a playability read is trusted/shown — the
# earnings calibration sweep tunes this; Tier-B default here.
DEFAULT_MIN_NQ = _env_int('BRIEF_REACTION_MIN_NQ', 12)


@lru_cache(maxsize=1)
def get_earnings_calibration() -> dict:
    """Resolve the playability lookback knobs.

    Tier A: the latest ``earnings_calibration`` row, written by the
    earnings calibration sweep (``scripts/calibrate_earnings.py``).
    Tier B: the env-var defaults above. Returns
    ``{'min_nq': int, 'lookback_quarters': int}``.

    Resilient — missing table / missing creds / empty table all resolve
    to Tier B so the brief keeps running. Cached per process; the brief
    runs as a fresh process each time, so it always sees the latest row.
    """
    tier_b = {'min_nq': DEFAULT_MIN_NQ,
              'lookback_quarters': DEFAULT_LOOKBACK_QUARTERS}
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return tier_b
    if not is_cloud_sql_configured():
        return tier_b
    try:
        df = query_to_dataframe(
            "SELECT min_nq, lookback_quarters FROM earnings_calibration "
            "ORDER BY calibration_date DESC LIMIT 1"
        )
    except Exception as e:
        # Config resolver (not a financial-data path): any query failure
        # — missing table, creds, transient error — resolves to Tier-B.
        # Mirrors lib/strategies/exit_config_overrides._latest_overrides.
        log.warning("earnings_calibration query failed (%s) — Tier-B",
                    type(e).__name__)
        return tier_b
    if df is None or df.empty:
        return tier_b
    row = df.iloc[0]
    min_nq = _to_float(row.get('min_nq'))
    lookback = _to_float(row.get('lookback_quarters'))
    return {
        'min_nq': int(min_nq) if min_nq is not None else DEFAULT_MIN_NQ,
        'lookback_quarters': (int(lookback) if lookback is not None
                              else DEFAULT_LOOKBACK_QUARTERS),
    }


def select_earnings_winner(
    results: list,
    min_predictions: int = 5000,
    min_quintile_spread: float = 0.0,
) -> Optional[dict]:
    """Pick the strategic winner from the earnings sweep's combo results.

    Each result is a dict with min_nq, lookback_quarters, n_predictions,
    overall_hit_rate, quintile_spread. The winner maximises
    quintile_spread (the score actually separates strong plays from
    weak) subject to hard gates:
      * n_predictions >= min_predictions   — enough out-of-sample sample
      * quintile_spread > min_quintile_spread

    Returns None when nothing clears the gates — the caller then leaves
    the current earnings_calibration untouched rather than applying a
    weak combo. The guardrails are the review, since the sweep
    auto-applies with no manual step.
    """
    eligible = [
        r for r in results
        if (r.get('n_predictions') or 0) >= min_predictions
        and (r.get('quintile_spread') or 0.0) > min_quintile_spread
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda r: r['quintile_spread'])


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


# Calibration-aware vehicle override (PR-B, 2026-05-22)
# ----------------------------------------------------
# When the 2026-05-21 backfill sweep computed options-side $ attribution
# across 2,533 Q5 events, the result was unambiguous: top-quintile picks
# have realized_vs_implied_ratio=0.636 (options OVERPRICED) and
# avg_short_strangle_pnl_pct=+20.3% (vs avg_long_straddle_pnl_pct=-9.5%
# and directional stock -$3.55/$1k). So the "right vehicle" for Q5 picks
# is NOT directional or long-volatility — it's SHORT premium.
#
# This helper overrides the archetype → action map for top-quintile picks
# when the live calibration row confirms the over-pricing pattern.
# Below Q5 (lower conviction), the archetype map still wins because the
# options edge is concentrated in the top quintile.

# Thresholds tuned to match the 2026-05-22 calibration row but
# loose enough that natural drift won't flip the recommendation.
_IC_RATIO_THRESHOLD     = 0.85   # realized must be < 85% of implied
_IC_STRANGLE_THRESHOLD  = 5.0    # short-strangle PnL must be > +5%

# Long-only-mode thresholds (2026-05-22 long-only-detail report):
# The 8% of Q5 events with realized/implied > 1.5 had 91% hit rate
# and +117% mean PnL on long straddle. The KEY predictor of those
# wins was IMPLIED MOVE SIZE — long-wins averaged implied = 12.1%,
# long-skips averaged 18.0%. Below 12% implied is the "easier to beat"
# zone; above 15% the premium is too rich for long premium to win
# on average. Between 12-15% is a coin-flip — fall back to archetype.
_LO_IMPLIED_SAFE_MAX     = 12.0   # below this → long premium has edge
_LO_IMPLIED_HARD_MAX     = 15.0   # above this → skip; premium too rich


def recommended_structure(
    archetype: Optional[str],
    score_quintile: Optional[str],
    calibration: Optional[dict] = None,
    implied_move_pct: Optional[float] = None,
    long_only: Optional[bool] = None,
) -> Optional[str]:
    """Return the brief's action tag for one earnings row.

    Default mode (long_only=False or unset): Q5 picks render 'IC'
    (Iron Condor) when the live calibration confirms over-pricing.
    Otherwise falls back to the archetype-driven map (CALL / PUT / STRDL).

    Long-only mode (long_only=True or env RECOMMEND_LONG_ONLY=true):
    For traders who only BUY premium. Never returns 'IC'. Instead:
      - If would-have-been IC: check per-event implied_move_pct.
        - Above _LO_IMPLIED_HARD_MAX (15%) → 'SKIP' (premium too rich)
        - Otherwise → archetype-driven LONG variant:
            bullish_trend → 'LONG CALL'
            bearish_trend → 'LONG PUT'
            anything else → 'LONG STRDL'
      - Otherwise: archetype-driven LONG variant (same map as above,
        no SKIP filter since these are Q1-Q4 picks where the
        over-pricing isn't confirmed).

    ``calibration`` is a dict with optional keys:
      - realized_vs_implied_ratio (float, e.g. 0.636)
      - avg_short_strangle_pnl_pct (float, e.g. 20.3)
    Both must be present and above thresholds for the override to
    fire. None / missing values cleanly fall through to the archetype
    map per CLAUDE.md §3.7 — no silent fallback to a hardcoded vehicle.

    ``implied_move_pct`` is the per-event implied move from the
    earnings_calendar row (NOT the calibration's avg). Only consulted
    in long_only mode. None = no filter (treat as 'unknown', keep
    the long recommendation).

    ``long_only`` overrides the env var when explicitly passed. The
    env var fallback supports running the brief in long-only mode
    without code changes.
    """
    _archetype_map = {
        'bullish_trend': 'CALL',
        'bearish_trend': 'PUT',
        'reversal_play': 'STRDL',
        'mixed':         'STRDL',
    }
    _long_archetype_map = {
        'bullish_trend': 'LONG CALL',
        'bearish_trend': 'LONG PUT',
        'reversal_play': 'LONG STRDL',
        'mixed':         'LONG STRDL',
    }

    if long_only is None:
        long_only = _env_long_only()

    archetype_action = (
        _long_archetype_map.get(archetype) if long_only
        else _archetype_map.get(archetype)
    ) if archetype else None

    # Below Q5: archetype map wins (the options edge is concentrated
    # in Q5 per the 2026-05-22 backtest).
    if score_quintile != 'Q5':
        return archetype_action

    # No calibration → can't confirm over/under-pricing. Return the
    # archetype map result (no IC override).
    if not calibration:
        return archetype_action

    ratio = calibration.get('realized_vs_implied_ratio')
    ss_pnl = calibration.get('avg_short_strangle_pnl_pct')
    is_over_priced = (
        ratio is not None and ss_pnl is not None
        and ratio < _IC_RATIO_THRESHOLD
        and ss_pnl > _IC_STRANGLE_THRESHOLD
    )

    if not is_over_priced:
        return archetype_action

    # Q5 + over-priced confirmed. Branch on mode.
    if not long_only:
        return 'IC'

    # Long-only mode: would have been IC, but the user only buys.
    # Filter by per-event implied move — when premium is rich
    # (>15% implied), even the directional long bet has historically
    # lost. Skip these instead of recommending a losing trade.
    if (implied_move_pct is not None
            and implied_move_pct > _LO_IMPLIED_HARD_MAX):
        return 'SKIP'
    # Otherwise return the long archetype map's recommendation.
    return archetype_action


def _env_long_only() -> bool:
    """Read RECOMMEND_LONG_ONLY env var as a bool.

    Truthy values: 'true', '1', 'yes', 'on' (case-insensitive).
    Anything else / unset → False (default = IC mode).
    """
    import os
    raw = (os.environ.get('RECOMMEND_LONG_ONLY') or '').strip().lower()
    return raw in {'true', '1', 'yes', 'on'}


def get_calibration_options_metrics() -> dict:
    """Pull the options-side calibration metrics from the latest row.

    Returns a dict of metrics the brief needs to drive
    ``recommended_structure()``. Falls back to an empty dict on any
    query failure — caller (`recommended_structure`) treats empty
    calibration as "no Q5 override available" and falls back to the
    archetype map. Resilient like ``get_earnings_calibration``.
    """
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}
    try:
        df = query_to_dataframe(
            "SELECT realized_vs_implied_ratio, avg_short_strangle_pnl_pct, "
            "avg_long_straddle_pnl_pct, avg_implied_move_pct, "
            "avg_realized_move_pct, n_with_options "
            "FROM earnings_calibration "
            "ORDER BY calibration_date DESC LIMIT 1"
        )
    except Exception as e:
        log.warning("earnings_calibration options-metrics query failed "
                    "(%s) — empty", type(e).__name__)
        return {}
    if df is None or df.empty:
        return {}
    row = df.iloc[0]
    out: dict = {}
    for k in ('realized_vs_implied_ratio', 'avg_short_strangle_pnl_pct',
              'avg_long_straddle_pnl_pct', 'avg_implied_move_pct',
              'avg_realized_move_pct'):
        v = _to_float(row.get(k))
        if v is not None:
            out[k] = v
    n_opts = row.get('n_with_options')
    if n_opts is not None:
        try:
            out['n_with_options'] = int(n_opts)
        except (TypeError, ValueError):
            pass
    return out


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
        lookback_quarters = get_earnings_calibration()['lookback_quarters']
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
    cal = get_earnings_calibration()
    if lookback_quarters is None:
        lookback_quarters = cal['lookback_quarters']
    min_nq = cal['min_nq']
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
        # Calibrated min-history gate (earnings_calibration.min_nq):
        # too few past quarters → the score isn't trustworthy, drop it.
        if (stats.get('n_q') or 0) < min_nq:
            r['playability_score'] = None
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


def earnings_session_schedule(start, end):
    """Reuse the merged canonical NYSE schedule, including DST/early closes."""
    from gcp.fetchers.evaluate_ew_strikes import nyse_sessions
    return nyse_sessions(start, end)


# Additive offline research profile; live SQL/default policy is unchanged.
LOCAL_EARNINGS_VERSION = 'earnings-local-admission-v1'
_LOCAL_FEATURES = ('reaction_gap_pct', 'pre_earnings_drift_10d_pct',
                   'sustain_5d_pct', 'direction_consistent_5d', 'is_reversal_5d')


def local_earnings_clock(value):
    """Require an explicit aware instant; a date alone is never a cutoff."""
    import pandas as pd
    if value is None or isinstance(value, (int, float)):
        raise ValueError('missing_or_invalid_observation_clock')
    instant = pd.Timestamp(value)
    if pd.isna(instant) or instant.tzinfo is None:
        raise ValueError('missing_or_naive_observation_clock')
    return instant.tz_convert('UTC')


def local_source_admission(receipt, event_id, observation_ts, mode):
    """Check declared source receipts, without certifying historical truth.

    recovered_at/acquired_at are preserved provenance, never substituted for
    observed_at. Strict mode needs an identified retained publication receipt.
    A syntactically valid declaration is not independent proof of publication.
    """
    clock = local_earnings_clock(observation_ts)
    if mode not in ('strict_pit', 'retrospective_current_vintage'):
        raise ValueError('invalid_local_mode')
    if not isinstance(receipt, dict) or not receipt.get('source_id'):
        raise ValueError('missing_source_identity')
    if receipt.get('event_id') != event_id or not event_id:
        raise ValueError('source_event_mismatch')
    observed = local_earnings_clock(receipt.get('observed_at'))
    acquired = local_earnings_clock(receipt.get('acquired_at'))
    if observed > acquired:
        raise ValueError('source_observation_after_acquisition')
    recovered = receipt.get('recovered_at')
    if recovered is not None and local_earnings_clock(recovered) < acquired:
        raise ValueError('recovery_before_acquisition')
    if mode == 'strict_pit':
        if not receipt.get('publication_evidence_id'):
            raise ValueError('missing_publication_evidence')
        if observed > clock:
            raise ValueError('source_not_known_at_cutoff')
    return {'source_id': receipt['source_id'], 'event_id': event_id,
            'observed_at': observed.isoformat(), 'acquired_at': acquired.isoformat(),
            'recovered_at': recovered,
            'publication_evidence_id': receipt.get('publication_evidence_id'),
            'eligibility': 'declared_receipt_only'}


def local_event_sessions(event):
    """Exact reported exchange session and D-1..D+10, using the shared calendar."""
    from datetime import date, timedelta
    from lib.earnings_reactions import earnings_session_schedule as nyse_schedule
    reported = date.fromisoformat(str(event['reported_date']))
    schedule = nyse_schedule(reported - timedelta(days=25), reported + timedelta(days=40))
    labels = [stamp.date() for stamp in schedule.index]
    if reported not in labels:
        raise ValueError('report_date_is_not_exchange_session')
    index = labels.index(reported)
    return schedule, index


def local_event_timing(event, observation_ts, mode):
    """Resolve only event-bound, agreeing, evidenced timing; unknown stays unknown."""
    import pandas as pd
    if not isinstance(event, dict):
        raise ValueError('missing_event_identity')
    event_id = event.get('event_id')
    if not event_id or not event.get('ticker'):
        raise ValueError('missing_event_identity')
    from datetime import date
    fiscal = date.fromisoformat(str(event['fiscal_date_ending']))
    if fiscal > date.fromisoformat(str(event['reported_date'])):
        raise ValueError('fiscal_end_after_report')
    release = local_earnings_clock(event.get('release_ts'))
    if release.tz_convert('America/New_York').date().isoformat() != str(event['reported_date']):
        raise ValueError('release_report_date_mismatch')
    schedule, index = local_event_sessions(event)
    opening = pd.Timestamp(schedule.iloc[index]['market_open'])
    closing = pd.Timestamp(schedule.iloc[index]['market_close'])
    declarations = event.get('timing_sources')
    if not declarations:
        raise ValueError('unknown_event_timing')
    choices = set()
    for source in declarations:
        if not isinstance(source, dict):
            raise ValueError('invalid_timing_source')
        timing_receipt = local_source_admission(source.get('receipt'), event_id, observation_ts, mode)
        if local_earnings_clock(timing_receipt['observed_at']) < release:
            raise ValueError('actual_release_not_observed')
        if source.get('basis') not in ('BMO', 'AMC'):
            raise ValueError('unknown_event_timing')
        choices.add(source['basis'])
    if len(choices) != 1:
        raise ValueError('conflicting_event_timing')
    basis = choices.pop()
    if (basis == 'BMO' and release >= opening) or (basis == 'AMC' and release < closing):
        raise ValueError('release_clock_timing_conflict')
    return basis, schedule, index



def normalize_local_event_dates(event, *, require_fiscal=True):
    """Copy accepted DB dates/JSON ISO dates into one identity representation."""
    from datetime import date
    if not isinstance(event, dict):
        raise ValueError('missing_event_identity')
    normalized = dict(event)
    reported = date.fromisoformat(str(event['reported_date']))
    normalized['reported_date'] = reported.isoformat()
    if require_fiscal or 'fiscal_date_ending' in event:
        fiscal = date.fromisoformat(str(event['fiscal_date_ending']))
        if fiscal > reported:
            raise ValueError('fiscal_end_after_report')
        normalized['fiscal_date_ending'] = fiscal.isoformat()
    return normalized


def admit_local_reaction(record, observation_ts, mode, *, gap_only=False):
    """Return an allowlisted mature row or an explicit rejection.

    Five-day classifier rows require every feature and its known-at receipt;
    raw SELECT-* extras (including D+10) never cross this boundary.
    """
    import math
    import pandas as pd
    try:
        clock = local_earnings_clock(observation_ts)
        event = normalize_local_event_dates(record['event'])
        from datetime import date
        fiscal = date.fromisoformat(str(event['fiscal_date_ending']))
        if fiscal > date.fromisoformat(str(event['reported_date'])):
            raise ValueError('fiscal_end_after_report')
        receipt = local_source_admission(record.get('receipt'), event.get('event_id'), clock, mode)
        basis, schedule, index = local_event_timing(event, clock, mode)
        release = local_earnings_clock(event['release_ts'])
        if release > clock:
            raise ValueError('event_not_released_at_cutoff')
        reaction_index = index if basis == 'BMO' else index + 1
        reaction_open = pd.Timestamp(schedule.iloc[reaction_index]['market_open'])
        required = ('reaction_gap_pct',) if gap_only else _LOCAL_FEATURES
        values = record['values']
        if not isinstance(values, dict) or not isinstance(record.get('field_known_at'), dict):
            raise ValueError('missing_feature_evidence')
        safe = {'ticker': event['ticker'], 'event_id': event['event_id'],
                'reported_date': event['reported_date'], 'fiscal_date_ending': fiscal.isoformat(),
                'reaction_basis': basis}
        for field in required:
            maturity = (pd.Timestamp(schedule.iloc[index + 5]['market_close'])
                        if field in ('sustain_5d_pct', 'direction_consistent_5d', 'is_reversal_5d')
                        else reaction_open)
            known = local_earnings_clock(record.get('field_known_at', {}).get(field))
            if known < maturity or known < release or maturity > clock:
                raise ValueError('feature_not_mature:' + field)
            if mode == 'strict_pit' and known > clock:
                raise ValueError('feature_not_known_at_cutoff:' + field)
            if known > local_earnings_clock(receipt['observed_at']):
                raise ValueError('feature_known_after_source_observation:' + field)
            value = values.get(field)
            if field in ('direction_consistent_5d', 'is_reversal_5d'):
                if type(value) is not bool:
                    raise ValueError('missing_or_invalid_feature:' + field)
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('missing_or_invalid_feature:' + field)
            safe[field] = value
        return {'available': True, 'row': safe, 'receipt': receipt}
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {'available': False, 'reason': str(exc)}


DAILY_PATH_VERSION = 'earnings-daily-path-v1'


def compute_daily_path_v1(event, daily, *, observation_ts, price_evidence=None,
                          mode='retrospective_current_vintage', schedule=None):
    """Completed DAILY closing steps, never intraday order or a forecast.

    Price evidence declares a coherent basis and actual receipt; it does not
    independently certify a provider's historical publication or issuer mapping.
    Unknowns remain None. A known first occurrence needs a complete prior prefix.
    """
    from datetime import date, timedelta
    import hashlib
    import json
    import pandas as pd

    payload = {'version': DAILY_PATH_VERSION, 'event_id': None,
               'reaction_basis': None, 'source_mode': mode if mode in ('strict_pit', 'retrospective_current_vintage') else None,
               'historical_publication_verified': False,
               'status': 'unavailable', 'reason': None, 'basis_id': None,
               'computed_at': pd.Timestamp.now(tz='UTC').isoformat(),
               'observation_ts': None, 'input_identity': None,
               'gap_sign': None, 'reaction_session': None,
               'pre_gap_close_session': None, 'window_end_session': None,
               'mature_at': None, 'expected_steps': None, 'observed_steps': None,
               'first_opposite_close_step': None, 'first_opposite_close_date': None,
               'closing_gap_fill_step': None, 'closing_gap_fill_date': None,
               'censored': None, 'per_metric': {}}
    try:
        clock = local_earnings_clock(observation_ts)
        payload['observation_ts'] = clock.isoformat()
        ev = normalize_local_event_dates(event)
        if not isinstance(ev.get('ticker'), str) or not 1 <= len(ev['ticker']) <= 10:
            raise ValueError('invalid_event_ticker')
        basis = ev.get('reaction_basis')
        if basis not in ('BMO', 'AMC'):
            raise ValueError('unknown_event_timing')
        event_id = f"{ev['ticker']}:{ev['fiscal_date_ending']}:{ev['reported_date']}"
        timing_source = ev.get('timing_source')
        if timing_source is not None and (not isinstance(timing_source,str) or len(timing_source)>128):
            raise ValueError('invalid_timing_source_identity')
        payload.update(event_id=event_id, reaction_basis=basis,
                       timing_source=timing_source)
        release = None
        if mode == 'strict_pit':
            if not ev.get('release_ts'):
                raise ValueError('missing_exact_release_clock_for_strict_pit')
            release = local_earnings_clock(ev['release_ts'])
            if release > clock:
                raise ValueError('event_not_released_at_cutoff')
            if release.tz_convert('America/New_York').date().isoformat() != ev['reported_date']:
                raise ValueError('release_report_date_mismatch')
        receipt = local_source_admission(price_evidence, event_id, clock, mode)
        basis_id = price_evidence.get('price_basis_id')
        if not isinstance(basis_id, str) or not basis_id.strip():
            raise ValueError('missing_price_basis')
        if len(basis_id) > 256 or not isinstance(receipt['source_id'], str) or len(receipt['source_id']) > 512:
            raise ValueError('oversize_or_invalid_price_identity')
        payload.update(basis_id=basis_id, source_identity=receipt['source_id'],
                       source_observed_at=receipt['observed_at'])
        reported = date.fromisoformat(ev['reported_date'])
        if schedule is None:
            schedule = earnings_session_schedule(reported - timedelta(days=14),
                                                  reported + timedelta(days=30))
        # A producer batch calendar may cover decades. A single descriptor
        # needs only this bounded canonical fragment, never a per-event scan
        # of the entire batch history. This changes no calendar algorithm.
        schedule = schedule.loc[(reported - timedelta(days=14)).isoformat():
                                (reported + timedelta(days=30)).isoformat()]
        labels = [stamp.date() for stamp in schedule.index]
        if reported not in labels:
            raise ValueError('report_date_is_not_exchange_session')
        d = labels.index(reported)
        if release is not None:
            opening = pd.Timestamp(schedule.iloc[d]['market_open'])
            closing = pd.Timestamp(schedule.iloc[d]['market_close'])
            if (basis == 'BMO' and release >= opening) or (basis == 'AMC' and release < closing):
                raise ValueError('release_clock_timing_conflict')
        start = d if basis == 'BMO' else d + 1
        stop = d + 5
        if d < 1 or stop >= len(labels):
            raise ValueError('insufficient_canonical_sessions')
        required = labels[start - 1:stop + 1]
        closes = {label: pd.Timestamp(schedule.iloc[i]['market_close'])
                  for i, label in enumerate(labels)}
        payload.update(reaction_session=labels[start].isoformat(),
                       pre_gap_close_session=labels[start - 1].isoformat(),
                       window_end_session=labels[stop].isoformat(),
                       mature_at=closes[labels[stop]].isoformat(),
                       expected_steps=stop - start + 1)
        # Slice before numeric validation/hash. Appended/perturbed future values
        # cannot enter a fixed decision's features or admitted-prefix identity.
        frame = daily.copy()
        frame['date'] = [date.fromisoformat(str(x)) for x in frame['date']]
        frame = frame[frame['date'].isin(required)]
        frame = frame[frame['date'].map(lambda label: closes[label] <= clock)]
        if frame['date'].duplicated().any():
            raise ValueError('duplicate_daily_session')
        frame = frame.sort_values('date')
        visible = [label for label in required if closes[label] <= clock]
        if list(frame['date']) != visible:
            raise ValueError('missing_daily_session')
        if len(frame) < 2:
            raise ValueError('reaction_close_not_mature')
        if local_earnings_clock(receipt['observed_at']) < closes[visible[-1]]:
            raise ValueError('price_observed_before_completed_bar')
        records = frame.to_dict('records')
        for row in records:
            nums = []
            for name in ('open', 'high', 'low', 'close'):
                value = row.get(name)
                if isinstance(value, bool):
                    raise ValueError('invalid_daily_price')
                value = float(value)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError('invalid_daily_price')
                nums.append(value)
            opening, high, low, closing = nums
            if high < max(opening, closing, low) or low > min(opening, closing):
                raise ValueError('incoherent_daily_ohlc')
        prefix = [{'date': r['date'].isoformat(), **{k: float(r[k]) for k in
                   ('open', 'high', 'low', 'close')}} for r in records]
        payload['input_identity'] = hashlib.sha256(json.dumps(
            {'event_id': event_id, 'basis': basis_id, 'prefix': prefix},
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        previous = float(records[0]['close'])
        opening = float(records[1]['open'])
        gap = opening - previous
        direction = 1 if gap > 0 else -1 if gap < 0 else 0
        observed = records[1:]
        payload.update(gap_sign=direction, observed_steps=len(observed))
        complete = closes[labels[stop]] <= clock
        if direction == 0:
            payload.update(status='not_applicable', reason='zero_opening_gap', censored=False)
            for metric in ('first_opposite_close', 'closing_gap_fill'):
                payload['per_metric'][metric] = {'available': False,
                    'status': 'not_applicable', 'reason': 'zero_opening_gap', 'censored': False}
            return {'available': True, 'payload': payload}
        prior_close = opening
        for step, row in enumerate(observed):
            closing = float(row['close'])
            change = closing - prior_close
            if payload['first_opposite_close_step'] is None and change * direction < 0:
                payload.update(first_opposite_close_step=step,
                               first_opposite_close_date=row['date'].isoformat())
            if payload['closing_gap_fill_step'] is None and (closing - previous) * direction <= 0:
                payload.update(closing_gap_fill_step=step,
                               closing_gap_fill_date=row['date'].isoformat())
            prior_close = closing
        payload['status'] = 'complete' if complete else 'maturing'
        payload['censored'] = (payload['first_opposite_close_step'] is None or
                                payload['closing_gap_fill_step'] is None) if complete else None
        for metric in ('first_opposite_close', 'closing_gap_fill'):
            found = payload[metric + '_step'] is not None
            found_date = payload[metric + '_date']
            payload['per_metric'][metric] = {
                'available': found or complete,
                'status': 'observed' if found else 'right_censored' if complete else 'not_yet_mature',
                'censored': False if found else True if complete else None,
                'mature_at': closes[date.fromisoformat(found_date)].isoformat()
                             if found else payload['mature_at'],
                'reason': None if found or complete else 'feature_not_mature'}
        if len(json.dumps(payload, allow_nan=False).encode()) > 4096:
            raise ValueError('daily_path_payload_exceeds_4KiB')
        return {'available': True, 'payload': payload}
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        payload.update(status='unavailable', reason=str(exc)[:160], censored=None,
                       first_opposite_close_step=None, first_opposite_close_date=None,
                       closing_gap_fill_step=None, closing_gap_fill_date=None)
        return {'available': False, 'reason': str(exc)[:160], 'payload': payload}


def database_daily_price_evidence(event, frame, *, schedule, observed_at, native=False):
    """Conservative current-DB declaration, not original provider/PIT proof.

    Only the merged AV raw-OHLC writer tags and explicit equal raw/adjusted
    closes qualify here. A changed/unclear adjustment factor is unavailable;
    this never guesses a split threshold, quote currency or issuer equivalence.
    Stronger retained receipts may be supplied by the same producer's caller.
    """
    from datetime import date
    import hashlib
    import json
    import pandas as pd
    try:
        ev = normalize_local_event_dates(event)
        from datetime import timedelta
        reported = date.fromisoformat(ev['reported_date'])
        schedule = schedule.loc[(reported-timedelta(days=30 if native else 14)).isoformat():
                                (reported+timedelta(days=30)).isoformat()]
        labels = [stamp.date() for stamp in schedule.index]
        d = labels.index(reported)
        start = d if ev.get('reaction_basis') == 'BMO' else d + 1
        required = labels[d-10:d+6] if native else labels[start - 1:d + 6]
        if (native and (d<10 or len(required)!=16)) or (not native and len(required) < (7 if ev.get('reaction_basis') == 'BMO' else 6)):
            raise ValueError('insufficient_canonical_sessions')
        rows = frame[frame['date'].isin(required)].copy()
        if not {'data_source', 'adjusted_close'} <= set(rows.columns):
            raise ValueError('missing_database_price_basis_metadata')
        if rows.empty or not rows['data_source'].isin(['alphavantage', 'alphavantage_daily']).all():
            raise ValueError('unrecognized_database_price_writer')
        raw = pd.to_numeric(rows['close'], errors='coerce')
        adjusted = pd.to_numeric(rows['adjusted_close'], errors='coerce')
        if not (raw.gt(0) & adjusted.gt(0) & raw.eq(adjusted)).all():
            raise ValueError('unresolved_adjustment_or_corporate_action')
        projection = rows[['date', 'open', 'high', 'low', 'close',
                           'adjusted_close', 'data_source']].copy()
        projection['date'] = projection['date'].map(str)
        digest = hashlib.sha256(projection.to_json(orient='records',
                        double_precision=15).encode()).hexdigest()
        stamp = local_earnings_clock(observed_at).isoformat()
        event_id = f"{ev['ticker']}:{ev['fiscal_date_ending']}:{ev['reported_date']}"
        return {'available': True, 'receipt': {
            'event_id': event_id, 'source_id': 'current-db-projection:' + digest,
            'observed_at': stamp, 'acquired_at': stamp,
            'price_basis_id': 'db-declared-av-raw-equal-adjusted-v1',
            'evidence_grade': 'current_db_writer_declaration_only'}}
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return {'available': False, 'reason': str(exc)[:160], 'receipt': None}


def admit_database_reaction(row, observation_ts, *, schedule=None):
    """Current-DB mature history adapter, not a strict original-PIT receipt.

    Accept only the same-event complete descriptor, explicit price basis and
    all native classifier fields. Never use the target or incomplete quarter.
    The strict retained-source `admit_local_reaction` contract stays separate.
    """
    import math
    import pandas as pd
    try:
        clock = local_earnings_clock(observation_ts)
        event = normalize_local_event_dates(row)
        report = pd.Timestamp(event['reported_date']).tz_localize('America/New_York')
        if report >= clock:
            raise ValueError('not_a_prior_event')
        p = row.get('daily_path_v1')
        event_id = f"{event['ticker']}:{event['fiscal_date_ending']}:{event['reported_date']}"
        if not isinstance(p, dict) or p.get('version') != DAILY_PATH_VERSION:
            raise ValueError('missing_admitted_daily_path')
        if p.get('event_id') != event_id or p.get('reaction_basis') != row.get('reaction_basis'):
            raise ValueError('reaction_identity_mismatch')
        if p.get('status') not in ('complete','not_applicable') or not p.get('basis_id'):
            raise ValueError('missing_complete_price_basis_evidence')
        import re
        if not isinstance(p.get('source_identity'),str) or not p['source_identity'].strip() or not re.fullmatch('[0-9a-f]{64}',str(p.get('input_identity',''))):
            raise ValueError('missing_source_or_input_identity')
        from datetime import date, timedelta
        reported = date.fromisoformat(event['reported_date'])
        if schedule is None:
            schedule = earnings_session_schedule(reported-timedelta(days=10), reported+timedelta(days=40))
        # A producer batch calendar may cover decades. A single descriptor
        # needs only this bounded canonical fragment, never a per-event scan
        # of the entire batch history. This changes no calendar algorithm.
        schedule = schedule.loc[(reported - timedelta(days=14)).isoformat():
                                (reported + timedelta(days=30)).isoformat()]
        labels = [stamp.date() for stamp in schedule.index]
        if reported not in labels:
            raise ValueError('report_date_is_not_exchange_session')
        d = labels.index(reported)
        if d+5 >= len(schedule):
            raise ValueError('missing_native_endpoint_session')
        expected_maturity = local_earnings_clock(schedule.iloc[d+5]['market_close'])
        if local_earnings_clock(p.get('mature_at')) != expected_maturity:
            raise ValueError('native_endpoint_maturity_mismatch')
        if expected_maturity > clock:
            raise ValueError('reaction_features_not_mature')
        if local_earnings_clock(p.get('source_observed_at')) < expected_maturity:
            raise ValueError('price_observed_before_completed_bar')
        native = p.get('per_metric',{}).get('native_classifier_inputs',{})
        if (native.get('version')!='earnings-native-inputs-v1' or native.get('available') is not True
                or native.get('event_id')!=event_id or native.get('reaction_basis')!=row.get('reaction_basis')
                or not native.get('source_identity')
                or not re.fullmatch('[0-9a-f]{64}',str(native.get('input_identity','')))):
            raise ValueError('unqualified_native_classifier_inputs')
        if native.get('basis_id')!=p.get('basis_id'):
            raise ValueError('native_dependency_basis_mismatch')
        if local_earnings_clock(native.get('source_observed_at'))<expected_maturity:
            raise ValueError('native_source_observed_before_completion')
        if local_earnings_clock(native.get('mature_at'))!=expected_maturity:
            raise ValueError('native_dependency_maturity_mismatch')
        for key in _LOCAL_FEATURES:
            val = row.get(key)
            if key in ('direction_consistent_5d','is_reversal_5d'):
                if type(val) is not bool:
                    raise ValueError('missing_or_invalid_feature:' + key)
            elif isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val):
                raise ValueError('missing_or_invalid_feature:' + key)
        return {'available':True,'row':dict(row, source_mode='retrospective_current_vintage',
                                           historical_publication_verified=False)}
    except (ValueError,TypeError,KeyError) as exc:
        return {'available':False,'reason':str(exc)}


def qualify_native_classifier_inputs(event, daily, *, observation_ts, price_evidence=None,
                                     schedule=None):
    """Qualify D-10..D+5 inputs separately from shorter daily path evidence.

    This metadata certifies only the existing five native classifier features;
    it never changes their arithmetic or certifies post-event D+10 fields.
    """
    from datetime import date,timedelta
    import hashlib,json,math
    import pandas as pd
    result={'version':'earnings-native-inputs-v1','available':False,'reason':None,
            'input_identity':None,'source_identity':None,'event_id':None,
            'prefix_start_session':None,'prefix_end_session':None,'mature_at':None}
    try:
        clock=local_earnings_clock(observation_ts)
        ev=normalize_local_event_dates(event)
        reported=date.fromisoformat(ev['reported_date'])
        result['event_id']=f"{ev['ticker']}:{ev['fiscal_date_ending']}:{ev['reported_date']}"
        result['reaction_basis']=ev.get('reaction_basis')
        if ev.get('reaction_basis') not in ('BMO','AMC'):
            raise ValueError('unknown_event_timing')
        if schedule is None:
            schedule=earnings_session_schedule(reported-timedelta(days=30),reported+timedelta(days=30))
        schedule=schedule.loc[(reported-timedelta(days=30)).isoformat():(reported+timedelta(days=30)).isoformat()]
        labels=[x.date() for x in schedule.index]
        if reported not in labels or labels.index(reported)<10:
            raise ValueError('missing_native_canonical_sessions')
        d=labels.index(reported);required=labels[d-10:d+6]
        if len(required)!=16:raise ValueError('missing_native_canonical_sessions')
        maturity=pd.Timestamp(schedule.iloc[d+5]['market_close'])
        result.update(prefix_start_session=required[0].isoformat(),prefix_end_session=required[-1].isoformat(),mature_at=maturity.isoformat())
        if maturity>clock:raise ValueError('native_features_not_mature')
        frame=daily.copy();frame['date']=[date.fromisoformat(str(v)) for v in frame['date']]
        frame=frame[frame['date'].isin(required)].sort_values('date')
        if frame['date'].duplicated().any():raise ValueError('duplicate_native_prefix_session')
        if list(frame['date'])!=required:raise ValueError('missing_native_prefix_session')
        receipt=local_source_admission(price_evidence,result['event_id'],clock,'retrospective_current_vintage')
        basis=price_evidence.get('price_basis_id')
        if not isinstance(basis,str) or not basis.strip() or len(basis)>256:raise ValueError('missing_native_price_basis')
        if not isinstance(receipt['source_id'],str) or len(receipt['source_id'])>512:raise ValueError('invalid_native_source_identity')
        if local_earnings_clock(receipt['observed_at'])<maturity:raise ValueError('native_source_observed_before_completion')
        records=[]
        for row in frame.to_dict('records'):
            values={}
            for key in ('open','high','low','close'):
                v=row.get(key)
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('invalid_native_ohlc')
                values[key]=float(v)
            if values['high']<max(values.values()) or values['low']>min(values.values()):raise ValueError('incoherent_native_ohlc')
            records.append({'date':row['date'].isoformat(),**values})
        result.update(available=True,reason=None,source_identity=receipt['source_id'],
                      source_observed_at=receipt['observed_at'],basis_id=basis,
                      input_identity=hashlib.sha256(json.dumps({'event_id':result['event_id'],'reaction_basis':ev['reaction_basis'],'basis_id':basis,'prefix':records},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest())
    except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
        result['reason']=str(exc)[:160]
    return result
