"""
The Strat candle classification system.

Encodes Rob Smith's methodology:
- Single-bar classification (1, 2U, 2D, 3) with inclusive inequalities
- Failed_2 sub-classification by close-vs-open
- Multi-bar combo detection (212, 312, 32, 22, 132, 322 reversals/continuations)
- Multi-inside compression states
- Full Timeframe Continuity (FTFC) scoring
- Per-combo bonus scoring (float, supports negative bonuses for opposing patterns)

See docs/STRAT_METHODOLOGY.md for the full spec.
"""

import pandas as pd
import numpy as np
from datetime import date as date_type
from typing import Any, Dict, Tuple, Optional

from lib.config import StratConfig


# ---------------------------------------------------------------------------
# Bonus tables
# ---------------------------------------------------------------------------
# Per §5 of docs/STRAT_METHODOLOGY.md. Float bonuses; opposing patterns
# carry negative bonuses to penalise mis-aligned signals.

COMBO_BONUS_CALL: Dict[str, float] = {
    # Bullish — positive contribution to a CALL signal
    '212_bull_reversal':     1.5,
    '312_bull_reversal':     1.5,
    '132_bull_continuation': 1.25,
    '322_bull_continuation': 1.25,
    '212_bull_continuation': 1.0,
    '32_bull_reversal':      1.0,
    '22_bull_reversal':      1.0,
    '22_bull_continuation':  0.75,
    'f2d_bull_reversal':     0.5,
    'clean_2u_bull':         0.25,
    # Bearish — opposing pattern, negative contribution
    '212_bear_reversal':     -1.5,
    '312_bear_reversal':     -1.5,
    '132_bear_continuation': -1.25,
    '322_bear_continuation': -1.25,
    '212_bear_continuation': -1.0,
    '32_bear_reversal':      -1.0,
    '22_bear_reversal':      -1.0,
    '22_bear_continuation':  -0.75,
    'f2u_bear_reversal':     -0.5,
    'clean_2d_bear':         -0.25,
}

# PUT bonuses are the sign-flipped mirror.
COMBO_BONUS_PUT: Dict[str, float] = {k: -v for k, v in COMBO_BONUS_CALL.items()}


class StratClassifier:
    """Classify candles and detect Strat patterns."""

    # Default FTFC weights — sums to 1.00. See §4 of methodology doc.
    DEFAULT_WEIGHTS: Dict[str, float] = {
        '5m':  0.05,
        '15m': 0.10,
        '1h':  0.15,
        '4h':  0.15,
        '12h': 0.15,
        '1d':  0.30,
        '1w':  0.10,
    }

    def __init__(self, strat_config: StratConfig = None):
        self.config = strat_config or StratConfig()
        if strat_config is not None and strat_config.ftfc_weights:
            self._default_weights = strat_config.ftfc_weights
        else:
            self._default_weights = self.DEFAULT_WEIGHTS

    # -----------------------------------------------------------------------
    # Single-candle classification
    # -----------------------------------------------------------------------

    @staticmethod
    def classify_candle(
        curr_high: float, curr_low: float,
        prev_high: float, prev_low: float,
    ) -> str:
        """Classify a single candle relative to the prior bar.

        Returns one of '1', '2U', '2D', '3'. Inclusive inequalities make the
        classification exhaustive — every non-first bar gets exactly one label.
        """
        higher_high = curr_high > prev_high
        lower_low = curr_low < prev_low

        if higher_high and lower_low:
            return '3'
        elif higher_high:
            return '2U'
        elif lower_low:
            return '2D'
        else:
            return '1'

    def classify_series(self, df: pd.DataFrame) -> pd.Series:
        """Vectorized classification for an OHLCV DataFrame.

        Expects 'High' and 'Low' columns. Returns a Series of labels
        aligned to the input index. First bar has no prior — labelled 'X'.
        """
        prev_high = df['High'].shift(1)
        prev_low = df['Low'].shift(1)
        curr_high = df['High']
        curr_low = df['Low']

        higher_high = curr_high > prev_high
        lower_low = curr_low < prev_low

        labels = pd.Series('X', index=df.index)
        labels[~higher_high & ~lower_low] = '1'
        labels[higher_high & ~lower_low] = '2U'
        labels[~higher_high & lower_low] = '2D'
        labels[higher_high & lower_low] = '3'

        labels.iloc[0] = 'X'
        return labels

    # -----------------------------------------------------------------------
    # Trigger levels
    # -----------------------------------------------------------------------

    @staticmethod
    def get_trigger_levels(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Return (trigger_high, trigger_low) — the prior bar's High and Low."""
        return df['High'].shift(1), df['Low'].shift(1)

    # -----------------------------------------------------------------------
    # Combo detection
    # -----------------------------------------------------------------------

    def detect_combos(self, df: pd.DataFrame, labels: pd.Series = None) -> pd.DataFrame:
        """Detect Strat combo patterns from classified candle data.

        Returns a DataFrame aligned to the input index with columns:
        - strat_candle: candle classification ('1', '2U', '2D', '3', 'X')
        - strat_combo: combo label per §2 of methodology doc, or 'none'
        - strat_setup: **inside-bar-pending** flag — True if and only
          if the latest bar is '1' (inside) AND the prior bar is
          directional ('2U' / '2D' / '3'). Read as "the next bar's
          break of the inside high or low triggers an entry."
        - trigger_high / trigger_low: breakout levels
        - consecutive_1s: rolling count of recent inside bars

        ## strat_setup vs strat_combo are orthogonal

        Common confusion (Track B audit B.5 / G.P1.6 flagged this as
        "internally inconsistent" before the orthogonality was
        documented): a `322_bull_continuation` row can — and routinely
        does — have `strat_setup=False`. That's correct.

        - `strat_combo` is the multi-bar pattern label (e.g. 322 fires
          when prev2='3', prev1='2U', and the latest bar is also '2U').
        - `strat_setup` only flips True when the latest bar is itself
          a '1' (inside bar) following a directional bar — i.e. when
          the trader should be watching the next bar's high/low to
          break in either direction.

        For continuation combos like 322 / 22 / clean_2u, the latest
        bar is by definition directional (a '2U' or '2D'), so
        `strat_setup` MUST be False; the entry already happened on
        that bar via the directional break, not on a pending inside
        bar. Tests in `tests/test_strat.py::TestSetupVsComboOrthogonality`
        lock this behaviour in.

        Priority order on collision (§3 of doc): higher-listed wins. Lower
        priorities only fill bars still tagged 'none'.
        """
        if labels is None:
            labels = self.classify_series(df)

        prev1 = labels.shift(1)
        prev2 = labels.shift(2)

        trigger_high, trigger_low = self.get_trigger_levels(df)
        one_bar_high = df['High'].shift(1)
        one_bar_low = df['Low'].shift(1)

        close_col = 'Close' if 'Close' in df.columns else 'Last'
        close = df[close_col] if close_col in df.columns else df['High']
        open_ = df['Open'] if 'Open' in df.columns else close

        result = pd.DataFrame(index=df.index)
        result['strat_candle'] = labels
        result['strat_combo'] = 'none'
        result['strat_setup'] = False
        result['trigger_high'] = trigger_high
        result['trigger_low'] = trigger_low

        none = lambda: result['strat_combo'] == 'none'

        # ── Priority 1: 3-bar reversals (X-1-2) ────────────────────────────
        mask_212_bull = (prev2 == '2D') & (prev1 == '1') & (df['High'] > one_bar_high)
        mask_212_bear = (prev2 == '2U') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_212_bull & none(), 'strat_combo'] = '212_bull_reversal'
        result.loc[mask_212_bear & none(), 'strat_combo'] = '212_bear_reversal'

        # ── Priority 2: 312 reversals (3-1-2) ──────────────────────────────
        mask_312_bull = (prev2 == '3') & (prev1 == '1') & (df['High'] > one_bar_high)
        mask_312_bear = (prev2 == '3') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_312_bull & none(), 'strat_combo'] = '312_bull_reversal'
        result.loc[mask_312_bear & none(), 'strat_combo'] = '312_bear_reversal'

        # ── Priority 3: 132 continuations (1-3-2) ──────────────────────────
        mask_132_bull = (prev2 == '1') & (prev1 == '3') & (labels == '2U')
        mask_132_bear = (prev2 == '1') & (prev1 == '3') & (labels == '2D')
        result.loc[mask_132_bull & none(), 'strat_combo'] = '132_bull_continuation'
        result.loc[mask_132_bear & none(), 'strat_combo'] = '132_bear_continuation'

        # ── Priority 4: 322 continuations (3-2-2) ──────────────────────────
        mask_322_bull = (prev2 == '3') & (prev1 == '2U') & (labels == '2U')
        mask_322_bear = (prev2 == '3') & (prev1 == '2D') & (labels == '2D')
        result.loc[mask_322_bull & none(), 'strat_combo'] = '322_bull_continuation'
        result.loc[mask_322_bear & none(), 'strat_combo'] = '322_bear_continuation'

        # ── Priority 5: 212 continuations (2-1-2 same direction) ───────────
        mask_212_bull_cont = (prev2 == '2U') & (prev1 == '1') & (df['High'] > one_bar_high)
        mask_212_bear_cont = (prev2 == '2D') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_212_bull_cont & none(), 'strat_combo'] = '212_bull_continuation'
        result.loc[mask_212_bear_cont & none(), 'strat_combo'] = '212_bear_continuation'

        # ── Priority 6: 32 reversals (3 followed by directional 2) ─────────
        # Direction of the prior outside bar's close determines the reversal:
        # if prev close was bullish, a 2D follows ⇒ bearish reversal.
        prev1_bullish_close = close.shift(1) > open_.shift(1)
        mask_32_bear = (prev1 == '3') & prev1_bullish_close & (labels == '2D')
        mask_32_bull = (prev1 == '3') & (~prev1_bullish_close) & (labels == '2U')
        result.loc[mask_32_bull & none(), 'strat_combo'] = '32_bull_reversal'
        result.loc[mask_32_bear & none(), 'strat_combo'] = '32_bear_reversal'

        # ── Priority 7: 22 reversals (mixed-direction 2-bar) ───────────────
        mask_22_bull_rev = (prev1 == '2D') & (labels == '2U')
        mask_22_bear_rev = (prev1 == '2U') & (labels == '2D')
        result.loc[mask_22_bull_rev & none(), 'strat_combo'] = '22_bull_reversal'
        result.loc[mask_22_bear_rev & none(), 'strat_combo'] = '22_bear_reversal'

        # ── Priority 8: 22 continuations (same-direction 2-bar) ────────────
        mask_22_bull = (prev1 == '2U') & (labels == '2U')
        mask_22_bear = (prev1 == '2D') & (labels == '2D')
        result.loc[mask_22_bull & none(), 'strat_combo'] = '22_bull_continuation'
        result.loc[mask_22_bear & none(), 'strat_combo'] = '22_bear_continuation'

        # ── Priority 8.5: 1-3-1 coil → expansion → coil ───────────────────
        # Inside (1) → outside (3) → inside (1). A pending, highly-actionable
        # compression after a volatility expansion — the break of THIS inside
        # bar's high/low is the trade (the "12hr-detector" 1-3-1 signal). The
        # latest bar is a '1', so strat_setup also flips True below.
        mask_131 = (prev2 == '1') & (prev1 == '3') & (labels == '1')
        result.loc[mask_131 & none(), 'strat_combo'] = '131_setup'

        # ── Priority 9-10: multi-inside compression ────────────────────────
        mask_111 = (prev2 == '1') & (prev1 == '1') & (labels == '1')
        mask_11 = (prev1 == '1') & (labels == '1')
        result.loc[mask_111 & none(), 'strat_combo'] = '111_inside_compression'
        result.loc[mask_11 & none(), 'strat_combo'] = '11_inside_compression'

        # ── Priority 11: Failed_2 (single bar, close-vs-open) ──────────────
        mask_f2u = (labels == '2U') & (close < open_)
        mask_f2d = (labels == '2D') & (close > open_)
        result.loc[mask_f2u & none(), 'strat_combo'] = 'f2u_bear_reversal'
        result.loc[mask_f2d & none(), 'strat_combo'] = 'f2d_bull_reversal'

        # ── Priority 12: clean directional bars ────────────────────────────
        mask_clean_2u = (labels == '2U') & (close >= open_)
        mask_clean_2d = (labels == '2D') & (close <= open_)
        result.loc[mask_clean_2u & none(), 'strat_combo'] = 'clean_2u_bull'
        result.loc[mask_clean_2d & none(), 'strat_combo'] = 'clean_2d_bear'

        # ── Setup / consecutive inside bars ────────────────────────────────
        # `strat_setup` is the inside-bar-pending flag, NOT a "any combo
        # is in force" flag. See class docstring for the orthogonality
        # contract. A 322 / 22 continuation row will publish strat_combo
        # populated AND strat_setup=False — that's the documented
        # behaviour, not a bug. Track B audit B.5 / G.P1.6 closed this
        # as not-a-bug after walking the truth table.
        result['strat_setup'] = (labels == '1') & (prev1.isin(['2U', '2D', '3']))
        result['consecutive_1s'] = (labels == '1').astype(int).rolling(window=2, min_periods=1).sum()

        return result

    # -----------------------------------------------------------------------
    # Full Timeframe Continuity
    # -----------------------------------------------------------------------

    def calculate_ftfc(
        self,
        tf_dataframes: Dict[str, pd.DataFrame],
        weights: Dict[str, float] = None,
    ) -> Tuple[float, str, Dict[str, str]]:
        """Calculate FTFC alignment score from multiple timeframes.

        Returns (score in [-1, 1], 'bullish'/'bearish'/'mixed', tf→label map).
        """
        if weights is None:
            weights = self._default_weights

        total_weight = 0.0
        weighted_sum = 0.0
        tf_labels: Dict[str, str] = {}

        for tf, df in tf_dataframes.items():
            if df.empty or len(df) < 2:
                continue

            label = self.classify_series(df).iloc[-1]
            tf_labels[tf] = label
            w = weights.get(tf, 0.0)

            if label == '2U':
                weighted_sum += w
            elif label == '2D':
                weighted_sum -= w

            total_weight += w

        if total_weight == 0:
            return 0.0, 'mixed', tf_labels

        score = weighted_sum / total_weight

        direction_threshold = self.config.ftfc_direction_threshold
        if score > direction_threshold:
            direction = 'bullish'
        elif score < -direction_threshold:
            direction = 'bearish'
        else:
            direction = 'mixed'

        return score, direction, tf_labels

    # -----------------------------------------------------------------------
    # Bonus scoring
    # -----------------------------------------------------------------------

    def get_strat_bonus(
        self,
        signal_direction: str,
        combo: str,
        ftfc_score: float,
        ftfc_threshold: float = None,
        orb_trend: int = 0,
    ) -> float:
        """Calculate bonus points for combined scoring.

        Returns a float — combo bonus per §5 of methodology doc plus
        FTFC alignment bonus and ORB alignment bonus. Opposing combos
        produce negative combo bonuses.
        """
        if ftfc_threshold is None:
            ftfc_threshold = self.config.ftfc_threshold

        ftfc_bonus = self.config.ftfc_bonus
        orb_alignment_bonus = self.config.orb_alignment_bonus

        bonus: float = 0.0

        # Combo contribution
        if signal_direction == 'CALL':
            bonus += COMBO_BONUS_CALL.get(combo, 0.0)
        elif signal_direction == 'PUT':
            bonus += COMBO_BONUS_PUT.get(combo, 0.0)

        # FTFC alignment
        if signal_direction == 'CALL':
            if ftfc_score >= ftfc_threshold:
                bonus += ftfc_bonus
            elif ftfc_score <= -ftfc_threshold:
                bonus -= ftfc_bonus
        elif signal_direction == 'PUT':
            if ftfc_score <= -ftfc_threshold:
                bonus += ftfc_bonus
            elif ftfc_score >= ftfc_threshold:
                bonus -= ftfc_bonus

        # ORB alignment
        if signal_direction == 'CALL' and orb_trend == 1:
            bonus += orb_alignment_bonus
        elif signal_direction == 'PUT' and orb_trend == -1:
            bonus += orb_alignment_bonus

        return bonus

    # -----------------------------------------------------------------------
    # Convenience
    # -----------------------------------------------------------------------

    def add_strat_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Classify candles and detect combos, returning the original
        DataFrame with Strat columns appended.
        """
        labels = self.classify_series(df)
        combos = self.detect_combos(df, labels)
        return pd.concat([df, combos], axis=1)


# ---------------------------------------------------------------------------
# Single source of truth for per-ticker live Strat + FTFC status.
#
# Both the 8:30 AM premarket-brief (gcp/premarket_brief.py) and the LLM
# pipeline analyst (lib/agents/summarizers.summarize_strat_status) call
# this helper instead of duplicating the daily-bars-to-FTFC composition.
# ---------------------------------------------------------------------------


def compute_strat_status(
    ticker: str,
    df: Optional[pd.DataFrame] = None,
    as_of: Optional[date_type] = None,
    timeframes: Optional[list[str]] = None,
    strat_config: Optional[StratConfig] = None,
    inclusive_today: bool = True,
) -> Dict[str, Any]:
    """Compute the latest Strat candle, in-force combo, and FTFC scoring.

    Loads daily OHLCV bars (via DataLoader.load_daily) when `df` is None
    so callers that already have a DataFrame in hand (e.g. premarket_brief
    inside its per-ticker loop) can pass it through and avoid a duplicate
    Cloud SQL read.

    Returns a dict with the StratSnapshot shape used by the LLM analyst
    plus richer fields the brief uses (`ftfc_labels`, `combo`).

    ``inclusive_today``:
      - True (default, legacy contract): ``as_of`` cutoff is
        **inclusive** — ``df.index <= as_of``. Used by backtests / EOD
        analytics that want "what would the strat say AT the close of
        day X" semantics. Today's row is included if it exists.
      - False (premarket contract): ``as_of`` cutoff is **strict** —
        ``df.index < as_of``. Mirrors what the 8:30 AM ET premarket
        brief sees (today's daily row hasn't been written yet OR has
        NULL OHLC). The insight pipeline runs in this mode so a
        ``INSIGHT_AS_OF=2026-05-06`` replay can't read 5/6's actual
        RTH close as ``iloc[-1]``.
    """
    # Timeframe keys must match RESAMPLE_RULES in lib/data_loader.py:
    #   '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w', '1mo'
    # Legacy 'D' / 'W' / 'M' are no longer accepted — every caller in
    # the repo passes the new keys after the strat-v2 deploy. Passing
    # an unknown key raises ValueError from build_multi_timeframe so
    # mistakes surface loudly instead of producing empty FTFC.
    timeframes = timeframes or ['1d', '1w', '1mo']

    if df is None:
        # Local import to avoid a strat→data_loader import cycle at
        # module load time. lib.data_loader imports from lib.strat
        # transitively via add_all_indicators in some flows.
        from lib.data_loader import DataLoader

        loader = DataLoader()
        df = loader.load_daily(ticker)
    else:
        # Caller passed an already-loaded frame; we still need the loader
        # to resample it to W/M for the FTFC dict.
        from lib.data_loader import DataLoader

        loader = DataLoader()

    if df is None or df.empty or len(df) < 2:
        return {"available": False, "reason": f"insufficient daily bars for {ticker}"}

    # Honour an explicit as_of by trimming bars after that date.
    #
    # Both sides of the comparison MUST share a timezone convention or
    # pandas raises TypeError (`Invalid comparison between dtype=
    # datetime64[ns] and Timestamp`). lib.data_loader.load_daily strips
    # tz from the index, so we normalize the cutoff to naive UTC. The
    # previous implementation only handled one direction of the
    # mismatch and swallowed the TypeError silently, which leaked
    # post-as_of bars into historical replays (insight reports for
    # ARM as_of=2026-04-20 were reading 2026-04-27 bars — see
    # docs/plans/INSIGHT_ZONE_HALLUCINATION_PLAN.md).
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tz is not None:
            cutoff = cutoff.tz_convert('UTC').tz_localize(None)
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_localize(None)
        if inclusive_today:
            # Inclusive cutoff: any bar on or before as_of's wall-clock
            # instant. A tz-aware datetime as_of=4/20 13:15 UTC still
            # admits the 4/20 midnight bar in this branch — preserves
            # the legacy backtest contract.
            df = df[df.index <= cutoff]
            reason_suffix = f"on or before {as_of}"
        else:
            # Strict cutoff: exclude ANY bar whose DATE equals as_of's
            # date. Daily bars are indexed at midnight, so comparing
            # against a partial-day cutoff (e.g. 13:15 UTC) would still
            # admit the midnight bar via `<`. Normalize to date for
            # deterministic premarket semantic.
            cutoff_date = cutoff.normalize()  # midnight of cutoff's date
            df = df[df.index < cutoff_date]
            reason_suffix = f"strictly before {as_of}"
        if df.empty or len(df) < 2:
            return {"available": False, "reason": f"insufficient bars {reason_suffix}"}

    strat = StratClassifier(strat_config=strat_config)

    # Daily candle + combo from the latest bar
    labels = strat.classify_series(df)
    combos = strat.detect_combos(df, labels)
    last_candle = labels.iloc[-1]
    last_combo = combos['strat_combo'].iloc[-1] if 'strat_combo' in combos.columns else None
    last_setup = combos['strat_setup'].iloc[-1] if 'strat_setup' in combos.columns else False

    # Multi-timeframe FTFC via the same loader.build_multi_timeframe path
    # the brief uses, so D/W/M classifications stay byte-identical.
    tf_dfs = loader.build_multi_timeframe(df, timeframes=timeframes)
    tf_classified = {tf: tf_df for tf, tf_df in tf_dfs.items() if not tf_df.empty}
    ftfc_score, ftfc_dir, ftfc_labels = strat.calculate_ftfc(tf_classified)

    # Trigger high/low from the prior bar (Strat trigger lines)
    prev = df.iloc[-2]
    trig_high = float(prev.get('High')) if pd.notna(prev.get('High')) else None
    trig_low = float(prev.get('Low')) if pd.notna(prev.get('Low')) else None

    # Best-effort `date` field — works whether the index is a DatetimeIndex
    # or the DataFrame has an explicit date column.
    bar_date = ""
    try:
        bar_date = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])
    except Exception:
        bar_date = ""

    return {
        "available": True,
        "ticker": ticker.upper(),
        "date": bar_date,
        "last_candle": str(last_candle) if last_candle else "1",
        "in_force_combo": str(last_combo) if last_combo else None,
        "strat_setup": bool(last_setup),
        "ftfc_score": float(ftfc_score) if ftfc_score is not None else 0.0,
        "ftfc_direction": ftfc_dir or "mixed",
        "ftfc_labels": dict(ftfc_labels) if ftfc_labels else {},
        "trigger_high": trig_high,
        "trigger_low": trig_low,
    }


# ---------------------------------------------------------------------------
# Historical Strat tape + upcoming setup, per higher timeframe.
#
# Powers the "ticker list → that ticker's previous strat over time" UI:
# given daily bars, resample up to daily / weekly / monthly / quarterly,
# classify every completed bar, and describe the in-progress (upcoming)
# period's break setup. Pure pandas — deterministic, hermetically testable.
# ---------------------------------------------------------------------------

# Timeframe keys (subset of lib.data_loader.RESAMPLE_RULES) the Strat ladder
# trades off levels: daily, weekly, monthly, quarterly.
STRAT_HISTORY_TIMEFRAMES: list[str] = ['1d', '1w', '1mo', '1q']


def _derive_strat_flags(combo: str, candle: str) -> Dict[str, bool]:
    """Continuation / reversal / inside / setup flags from a combo label +
    candle. Mirrors the regex derivation in strat_data_builder so the API
    and the persisted features agree."""
    c = combo or 'none'
    return {
        "is_continuation": "continuation" in c,
        "is_reversal": "reversal" in c,
        "is_inside": candle == '1',
        # 131 and any inside-after-directional bar is a pending break setup
        "is_setup": candle == '1',
    }


def _last_directional(labels: pd.Series) -> Optional[str]:
    """Most recent '2U'/'2D' label scanning backward (the bar whose direction
    a next-bar break would continue or reverse). None if none found."""
    for lab in reversed(list(labels)):
        if lab in ('2U', '2D'):
            return lab
    return None


def _upcoming_setup(tf_df: pd.DataFrame, labels: pd.Series,
                    combos: pd.DataFrame) -> Dict[str, Any]:
    """Describe the break setup for the NEXT bar of this timeframe.

    The trigger lines are the latest completed bar's High/Low (Strat
    triggers). A break above → '2U', below → '2D'; continuation vs reversal
    is read against the most recent directional bar. The 50% line (bar
    midpoint) mirrors the detector's "50% Trigger".
    """
    last = tf_df.iloc[-1]
    last_candle = str(labels.iloc[-1])
    last_combo = str(combos['strat_combo'].iloc[-1])
    th = float(last['High']) if pd.notna(last['High']) else None
    tl = float(last['Low']) if pd.notna(last['Low']) else None
    mid = (th + tl) / 2 if (th is not None and tl is not None) else None

    prior_dir = _last_directional(labels)
    # break_up makes a 2U: continuation if the prevailing direction is up,
    # else a reversal of the down move (22 reversal). Symmetric for break_down.
    if prior_dir == '2U':
        break_up, break_down = '2U continuation', '2D reversal'
    elif prior_dir == '2D':
        break_up, break_down = '2U reversal', '2D continuation'
    else:
        break_up, break_down = '2U', '2D'

    return {
        "basis_candle": last_candle,
        "basis_combo": last_combo,
        "is_inside_setup": last_candle == '1',          # cleanest 1 / 131 coil
        "trigger_high": th,
        "trigger_low": tl,
        "mid_trigger": mid,
        "break_up": break_up,
        "break_down": break_down,
    }


def _bar_record(idx, row, candle: str, combo: str) -> Dict[str, Any]:
    flags = _derive_strat_flags(combo, candle)
    try:
        period = str(idx.date()) if hasattr(idx, 'date') else str(idx)
    except Exception:
        period = str(idx)
    return {
        "period": period,
        "open": float(row['Open']) if pd.notna(row.get('Open')) else None,
        "high": float(row['High']) if pd.notna(row.get('High')) else None,
        "low": float(row['Low']) if pd.notna(row.get('Low')) else None,
        "close": float(row['Close']) if pd.notna(row.get('Close')) else None,
        "candle": candle,
        "combo": combo,
        **flags,
    }


def compute_strat_history(
    ticker: str,
    df: Optional[pd.DataFrame] = None,
    timeframes: Optional[list[str]] = None,
    lookback: int = 20,
    strat_config: Optional[StratConfig] = None,
) -> Dict[str, Any]:
    """Historical Strat classification per timeframe + the upcoming setup.

    Resamples daily bars up to each requested timeframe (daily/weekly/monthly/
    quarterly), classifies every completed bar (candle + combo), and returns
    the last ``lookback`` bars plus the in-progress period's break setup.

    Returns::

        {
          "available": True, "ticker": "AAPL",
          "timeframes": {
            "1d": {"history": [ {period, o,h,l,c, candle, combo, is_* }... ],
                   "current": {...latest completed bar...},
                   "upcoming": {trigger_high, trigger_low, mid_trigger,
                                break_up, break_down, is_inside_setup, ...}},
            "1w": {...}, "1mo": {...}, "1q": {...},
          }
        }

    Pure-function given ``df``; when ``df`` is None it loads daily bars via
    DataLoader (a network read). Fails loud on insufficient data (Rule 3.7 —
    no synthetic fallback).
    """
    from lib.data_loader import DataLoader

    timeframes = timeframes or STRAT_HISTORY_TIMEFRAMES
    loader = DataLoader()
    if df is None:
        df = loader.load_daily(ticker)
    if df is None or df.empty or len(df) < 2:
        return {"available": False, "ticker": ticker.upper(),
                "reason": f"insufficient daily bars for {ticker}"}

    strat = StratClassifier(strat_config=strat_config)
    out: Dict[str, Any] = {"available": True, "ticker": ticker.upper(), "timeframes": {}}

    for tf in timeframes:
        # '1d' is the daily frame itself; higher TFs resample from it.
        tf_df = df if tf == '1d' else loader.aggregate_to_timeframe(df, tf)
        # Drop incomplete trailing rows with NaN OHLC from resampling gaps.
        tf_df = tf_df.dropna(subset=['High', 'Low', 'Close'])
        if tf_df.empty or len(tf_df) < 2:
            out["timeframes"][tf] = {"available": False,
                                     "reason": f"insufficient {tf} bars"}
            continue
        labels = strat.classify_series(tf_df)
        combos = strat.detect_combos(tf_df, labels)
        records = [
            _bar_record(idx, tf_df.loc[idx], str(labels.loc[idx]),
                        str(combos['strat_combo'].loc[idx]))
            for idx in tf_df.index
        ]
        history = records[-lookback:]
        out["timeframes"][tf] = {
            "available": True,
            "history": history,
            "current": history[-1],
            "upcoming": _upcoming_setup(tf_df, labels, combos),
        }

    return out
