"""
The Strat candle classification system.

Encodes Rob Smith's methodology (see docs/STRAT_METHODOLOGY.md):
- Candle type labeling (1, 2U, 2D, 3) on any timeframe
- Combo pattern detection (212, 312, 132, 322, 22, 32, Failed_2, multi-inside)
- Full Timeframe Continuity (FTFC) scoring across 7 timeframes
- Integration bonus for combined signal scoring (float, supports negatives)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from lib.config import StratConfig


# ─── Per-combo bonus values (see docs/STRAT_METHODOLOGY.md §18) ──────────

COMBO_BONUS_CALL: Dict[str, float] = {
    'f2d_bull_reversal': 1.0,
    'f2u_bear_reversal': -0.5,
    '212_bull_reversal': 1.0,
    '212_bear_reversal': 0.0,
    '212_bull_continuation': 0.75,
    '212_bear_continuation': 0.0,
    '312_bull_reversal': 1.0,
    '312_bear_reversal': 0.0,
    '132_bull_continuation': 1.0,
    '132_bear_continuation': 0.0,
    '322_bull_continuation': 0.75,
    '322_bear_continuation': 0.0,
    '32_bull_reversal': 0.75,
    '32_bear_reversal': 0.0,
    '22_bull_reversal': 1.0,
    '22_bear_reversal': -0.5,
    '22_bull_continuation': 0.5,
    '22_bear_continuation': 0.0,
    'clean_2u_bull': 0.25,
    'clean_2d_bear': 0.0,
    '11_inside_compression': 0.0,
    '111_inside_compression': 0.0,
    'none': 0.0,
}

COMBO_BONUS_PUT: Dict[str, float] = {
    'f2d_bull_reversal': -0.5,
    'f2u_bear_reversal': 1.0,
    '212_bull_reversal': 0.0,
    '212_bear_reversal': 1.0,
    '212_bull_continuation': 0.0,
    '212_bear_continuation': 0.75,
    '312_bull_reversal': 0.0,
    '312_bear_reversal': 1.0,
    '132_bull_continuation': 0.0,
    '132_bear_continuation': 1.0,
    '322_bull_continuation': 0.0,
    '322_bear_continuation': 0.75,
    '32_bull_reversal': 0.0,
    '32_bear_reversal': 0.75,
    '22_bull_reversal': -0.5,
    '22_bear_reversal': 1.0,
    '22_bull_continuation': 0.0,
    '22_bear_continuation': 0.5,
    'clean_2u_bull': 0.0,
    'clean_2d_bear': 0.25,
    '11_inside_compression': 0.0,
    '111_inside_compression': 0.0,
    'none': 0.0,
}


class StratClassifier:
    """Classify candles and detect Strat patterns."""

    # Default FTFC weights by timeframe (higher TF = more weight).
    # See docs/STRAT_METHODOLOGY.md §16.
    DEFAULT_WEIGHTS = {
        '5m': 0.05,
        '15m': 0.10,
        '1h': 0.15,
        '4h': 0.15,
        '12h': 0.15,
        '1d': 0.30,
        '1w': 0.10,
    }

    def __init__(self, strat_config: StratConfig = None):
        self.config = strat_config or StratConfig()
        if strat_config is not None and strat_config.ftfc_weights:
            self._default_weights = strat_config.ftfc_weights
        else:
            self._default_weights = self.DEFAULT_WEIGHTS

    # ───────────────────────────────────────────────────────────────────────
    # Single-candle classification
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def classify_candle(
        curr_high: float, curr_low: float,
        prev_high: float, prev_low: float,
    ) -> str:
        """Classify a single candle relative to the prior bar.

        Returns: '1' (inside), '2U' (up), '2D' (down), '3' (outside)
        Uses inclusive inequalities so classification is exhaustive.
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
        """Vectorized classification for an entire OHLCV DataFrame.

        Expects 'High' and 'Low' columns. Returns a Series of labels.
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

        # First bar has no prior — mark as unknown
        labels.iloc[0] = 'X'

        return labels

    # ───────────────────────────────────────────────────────────────────────
    # Trigger levels
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_trigger_levels(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Return (trigger_high, trigger_low) — prior bar's High and Low."""
        return df['High'].shift(1), df['Low'].shift(1)

    # ───────────────────────────────────────────────────────────────────────
    # Combo pattern detection
    # ───────────────────────────────────────────────────────────────────────

    def detect_combos(self, df: pd.DataFrame, labels: pd.Series = None) -> pd.DataFrame:
        """Detect Strat combo patterns from classified candle data.

        Returns a DataFrame aligned to the input index with columns:
        - strat_candle: candle classification (1/2U/2D/3)
        - strat_combo: combo label or 'none'
        - strat_setup: True if a combo setup is forming
        - trigger_high / trigger_low: breakout levels

        Priority order (highest first, see docs/STRAT_METHODOLOGY.md §17):
          212 REV > 312 REV > 212 CON > 132 > 322 > 32 REV >
          22 REV > 22 CON > 11/111 > Failed_2 > Clean 2U/2D
        """
        if labels is None:
            labels = self.classify_series(df)

        prev1 = labels.shift(1)   # 1 bar ago
        prev2 = labels.shift(2)   # 2 bars ago
        prev3 = labels.shift(3)   # 3 bars ago (for triple inside)

        trigger_high, trigger_low = self.get_trigger_levels(df)
        one_bar_high = df['High'].shift(1)  # the inside bar's high
        one_bar_low = df['Low'].shift(1)    # the inside bar's low

        close_col = 'Close' if 'Close' in df.columns else 'Last'
        close = df[close_col] if close_col in df.columns else df['High']
        open_col = df['Open'] if 'Open' in df.columns else close

        result = pd.DataFrame(index=df.index)
        result['strat_candle'] = labels
        result['strat_combo'] = 'none'
        result['strat_setup'] = False
        result['trigger_high'] = trigger_high
        result['trigger_low'] = trigger_low

        # Helper: only assign where strat_combo is still 'none'
        def _empty():
            return result['strat_combo'] == 'none'

        # ── Priority 1: 212 REV (3-bar reversal after coil) ──────────
        mask_212_bull = (prev2 == '2D') & (prev1 == '1') & (df['High'] > one_bar_high)
        result.loc[mask_212_bull, 'strat_combo'] = '212_bull_reversal'

        mask_212_bear = (prev2 == '2U') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_212_bear, 'strat_combo'] = '212_bear_reversal'

        # ── Priority 2: 312 REV (outside bar digested) ───────────────
        mask_312_bull = (prev2 == '3') & (prev1 == '1') & (df['High'] > one_bar_high)
        result.loc[mask_312_bull & _empty(), 'strat_combo'] = '312_bull_reversal'

        mask_312_bear = (prev2 == '3') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_312_bear & _empty(), 'strat_combo'] = '312_bear_reversal'

        # ── Priority 3: 212 CON (continuation after coil) ────────────
        mask_212con_bull = (prev2 == '2U') & (prev1 == '1') & (df['High'] > one_bar_high)
        result.loc[mask_212con_bull & _empty(), 'strat_combo'] = '212_bull_continuation'

        mask_212con_bear = (prev2 == '2D') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_212con_bear & _empty(), 'strat_combo'] = '212_bear_continuation'

        # ── Priority 4: 132 (coil, explode, follow-through) ──────────
        mask_132_bull = (prev2 == '1') & (prev1 == '3') & (labels == '2U')
        result.loc[mask_132_bull & _empty(), 'strat_combo'] = '132_bull_continuation'

        mask_132_bear = (prev2 == '1') & (prev1 == '3') & (labels == '2D')
        result.loc[mask_132_bear & _empty(), 'strat_combo'] = '132_bear_continuation'

        # ── Priority 5: 322 (expansion then direction confirmed) ─────
        mask_322_bull = (prev2 == '3') & (prev1 == '2U') & (labels == '2U')
        result.loc[mask_322_bull & _empty(), 'strat_combo'] = '322_bull_continuation'

        mask_322_bear = (prev2 == '3') & (prev1 == '2D') & (labels == '2D')
        result.loc[mask_322_bear & _empty(), 'strat_combo'] = '322_bear_continuation'

        # ── Priority 6: 32 REV (outside bar then directional) ────────
        prev1_bullish_close = (
            close.shift(1) > open_col.shift(1)
            if 'Open' in df.columns
            else pd.Series(False, index=df.index)
        )
        mask_32_bull = (prev1 == '3') & (~prev1_bullish_close) & (labels == '2U')
        result.loc[mask_32_bull & _empty(), 'strat_combo'] = '32_bull_reversal'

        mask_32_bear = (prev1 == '3') & prev1_bullish_close & (labels == '2D')
        result.loc[mask_32_bear & _empty(), 'strat_combo'] = '32_bear_reversal'

        # ── Priority 7: 22 REV (consecutive opposite-direction) ──────
        mask_22rev_bull = (prev1 == '2D') & (labels == '2U')
        result.loc[mask_22rev_bull & _empty(), 'strat_combo'] = '22_bull_reversal'

        mask_22rev_bear = (prev1 == '2U') & (labels == '2D')
        result.loc[mask_22rev_bear & _empty(), 'strat_combo'] = '22_bear_reversal'

        # ── Priority 8: 22 CON (consecutive same-direction) ──────────
        mask_22con_bull = (prev1 == '2U') & (labels == '2U')
        result.loc[mask_22con_bull & _empty(), 'strat_combo'] = '22_bull_continuation'

        mask_22con_bear = (prev1 == '2D') & (labels == '2D')
        result.loc[mask_22con_bear & _empty(), 'strat_combo'] = '22_bear_continuation'

        # ── Priority 9: Multi-inside (1-1 and 1-1-1 compression) ─────
        mask_111 = (prev3 == '1') & (prev2 == '1') & (prev1 == '1') & (labels == '1')
        result.loc[mask_111 & _empty(), 'strat_combo'] = '111_inside_compression'

        mask_11 = (prev1 == '1') & (labels == '1')
        result.loc[mask_11 & _empty(), 'strat_combo'] = '11_inside_compression'

        # ── Priority 10: Failed 2U / Failed 2D (close vs open) ───────
        # See docs/STRAT_METHODOLOGY.md §2. A bar that breaks one side
        # of the prior range but closes opposite to the break direction.
        # close < open = bearish close; close > open = bullish close.
        mask_f2u = (labels == '2U') & (close < open_col)
        result.loc[mask_f2u & _empty(), 'strat_combo'] = 'f2u_bear_reversal'

        mask_f2d = (labels == '2D') & (close > open_col)
        result.loc[mask_f2d & _empty(), 'strat_combo'] = 'f2d_bull_reversal'

        # ── Priority 11: Clean 2U / Clean 2D (no multi-bar context) ──
        mask_clean_2u = (labels == '2U') & (close >= open_col)
        result.loc[mask_clean_2u & _empty(), 'strat_combo'] = 'clean_2u_bull'

        mask_clean_2d = (labels == '2D') & (close <= open_col)
        result.loc[mask_clean_2d & _empty(), 'strat_combo'] = 'clean_2d_bear'

        # ── Setup detection (inside bar forming after directional) ────
        result['strat_setup'] = (labels == '1') & (prev1.isin(['2U', '2D', '3']))

        # ── Consecutive inside bars (compression counter) ────────────
        result['consecutive_1s'] = (
            (labels == '1').astype(int).rolling(window=2, min_periods=1).sum()
        )

        return result

    # ───────────────────────────────────────────────────────────────────────
    # Full Timeframe Continuity (FTFC)
    # ───────────────────────────────────────────────────────────────────────

    def calculate_ftfc(
        self,
        tf_dataframes: Dict[str, pd.DataFrame],
        weights: Dict[str, float] = None,
    ) -> Tuple[float, str, Dict[str, str]]:
        """Calculate FTFC alignment score from multiple timeframes.

        Parameters
        ----------
        tf_dataframes : dict mapping timeframe label -> OHLCV DataFrame
        weights : optional dict of timeframe -> weight (must sum to ~1.0)

        Returns
        -------
        score : float between -1.0 (all bearish) and +1.0 (all bullish)
        direction : 'bullish', 'bearish', or 'mixed'
        labels : dict of timeframe -> latest strat type
        """
        if weights is None:
            weights = self._default_weights

        total_weight = 0.0
        weighted_sum = 0.0
        tf_labels = {}

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

    # ───────────────────────────────────────────────────────────────────────
    # Signal integration bonus
    # ───────────────────────────────────────────────────────────────────────

    def get_strat_bonus(
        self,
        signal_direction: str,
        combo: str,
        ftfc_score: float,
        ftfc_threshold: float = None,
        orb_trend: int = 0,
    ) -> float:
        """Calculate bonus points for combined scoring.

        Parameters
        ----------
        signal_direction : 'CALL' or 'PUT'
        combo : strat combo label from detect_combos()
        ftfc_score : -1.0 to +1.0 from calculate_ftfc()
        ftfc_threshold : minimum absolute FTFC score for bonus
        orb_trend : ORB trend direction (1=bullish, -1=bearish, 0=neutral)

        Returns
        -------
        bonus : float (can be negative if pattern/FTFC opposes direction)
        """
        if ftfc_threshold is None:
            ftfc_threshold = self.config.ftfc_threshold

        bonus = 0.0

        # Per-combo bonus from the scoring tables
        if signal_direction == 'CALL':
            bonus += COMBO_BONUS_CALL.get(combo, 0.0)
        elif signal_direction == 'PUT':
            bonus += COMBO_BONUS_PUT.get(combo, 0.0)

        # FTFC alignment bonus / penalty
        if signal_direction == 'CALL':
            if ftfc_score >= ftfc_threshold:
                bonus += 1.0
            elif ftfc_score <= -ftfc_threshold:
                bonus -= 1.0
        elif signal_direction == 'PUT':
            if ftfc_score <= -ftfc_threshold:
                bonus += 1.0
            elif ftfc_score >= ftfc_threshold:
                bonus -= 1.0

        # ORB alignment bonus
        orb_alignment_bonus = self.config.orb_alignment_bonus
        if signal_direction == 'CALL' and orb_trend == 1:
            bonus += orb_alignment_bonus
        elif signal_direction == 'PUT' and orb_trend == -1:
            bonus += orb_alignment_bonus

        return bonus

    # ───────────────────────────────────────────────────────────────────────
    # Convenience: classify and add Strat columns to a DataFrame
    # ───────────────────────────────────────────────────────────────────────

    def add_strat_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Classify candles and detect combos, returning the original
        DataFrame with Strat columns appended.
        """
        labels = self.classify_series(df)
        combos = self.detect_combos(df, labels)
        return pd.concat([df, combos], axis=1)
