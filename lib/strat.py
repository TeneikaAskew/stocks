"""
The Strat candle classification system.

Encodes Rob Smith's methodology:
- Candle type labeling (1, 2U, 2D, 3) on any timeframe
- Combo pattern detection (2-1-2 reversals, 3-1-2, continuations)
- Full Timeframe Continuity (FTFC) scoring across multiple timeframes
- Integration bonus for combined signal scoring (+0 to +3 points)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

from lib.config import StratConfig


class StratClassifier:
    """Classify candles and detect Strat patterns."""

    # Default FTFC weights by timeframe (higher TF = more weight)
    DEFAULT_WEIGHTS = {
        '5m': 0.10,
        '15m': 0.20,
        '1h': 0.25,
        'D': 0.35,
        'W': 0.10,
    }

    def __init__(self, strat_config: StratConfig = None):
        self.config = strat_config or StratConfig()
        # If config provides ftfc_weights, use those as the instance default
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

        Returns: '1' (inside), '2U' (up), '2D' (down), '3' (outside)
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

        # First bar has no prior -- mark as unknown
        labels.iloc[0] = 'X'

        return labels

    # -----------------------------------------------------------------------
    # Trigger levels
    # -----------------------------------------------------------------------

    @staticmethod
    def get_trigger_levels(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Return (trigger_high, trigger_low) -- prior bar's High and Low.

        Breaking above trigger_high = bullish trigger.
        Breaking below trigger_low = bearish trigger.
        """
        return df['High'].shift(1), df['Low'].shift(1)

    # -----------------------------------------------------------------------
    # Combo pattern detection
    # -----------------------------------------------------------------------

    def detect_combos(self, df: pd.DataFrame, labels: pd.Series = None) -> pd.DataFrame:
        """Detect Strat combo patterns from classified candle data.

        Returns a DataFrame aligned to the input index with columns:
        - strat_type: candle classification
        - strat_combo: combo label (e.g., '2D-1-2U_reversal') or 'none'
        - strat_setup: True if a combo setup is forming (2-bar into inside bar)
        - trigger_high / trigger_low: breakout levels
        """
        if labels is None:
            labels = self.classify_series(df)

        prev1 = labels.shift(1)  # 1 bar ago
        prev2 = labels.shift(2)  # 2 bars ago

        trigger_high, trigger_low = self.get_trigger_levels(df)
        one_bar_high = df['High'].shift(1)  # the inside bar's high
        one_bar_low = df['Low'].shift(1)   # the inside bar's low

        close_col = 'Close' if 'Close' in df.columns else 'Last'
        close = df[close_col] if close_col in df.columns else df['High']  # fallback

        result = pd.DataFrame(index=df.index)
        result['strat_type'] = labels
        result['strat_combo'] = 'none'
        result['strat_setup'] = False
        result['trigger_high'] = trigger_high
        result['trigger_low'] = trigger_low

        # --- Reversal combos ---

        # 2D-1-2U Reversal (Bullish): bearish move -> compression -> bullish breakout
        mask_212_bull = (prev2 == '2D') & (prev1 == '1') & (df['High'] > one_bar_high)
        result.loc[mask_212_bull, 'strat_combo'] = '2D-1-2U_reversal'

        # 2U-1-2D Reversal (Bearish): bullish move -> compression -> bearish breakout
        mask_212_bear = (prev2 == '2U') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_212_bear, 'strat_combo'] = '2U-1-2D_reversal'

        # 3-1-2U Reversal (Bullish): outside bar -> compression -> bullish
        mask_312_bull = (prev2 == '3') & (prev1 == '1') & (df['High'] > one_bar_high)
        result.loc[mask_312_bull, 'strat_combo'] = '3-1-2U_reversal'

        # 3-1-2D Reversal (Bearish): outside bar -> compression -> bearish
        mask_312_bear = (prev2 == '3') & (prev1 == '1') & (df['Low'] < one_bar_low)
        result.loc[mask_312_bear, 'strat_combo'] = '3-1-2D_reversal'

        # --- Failed 2U / Failed 2D (RevStrat reversals) ---
        #
        # The current bar prints as a directional 2 but closes back inside the
        # PRIOR bar's range — i.e. the breakout failed and reversed. These are
        # the highest-prob single-bar reversal signals in the community recaps
        # (see tradingview-pine-scripts/strat-assistant-v2 for the Pine
        # equivalents named 122_RevStrat_Bull/Bear). Locked definition:
        #   Failed_2U: bar prints higher high than prior bar but closes back
        #              inside prior bar's range (close <= prev_high).
        #   Failed_2D: bar prints lower low than prior bar but closes back
        #              inside prior bar's range (close >= prev_low).
        prev_high = df['High'].shift(1)
        prev_low = df['Low'].shift(1)
        mask_failed_2u = (labels == '2U') & (close <= prev_high)
        mask_failed_2d = (labels == '2D') & (close >= prev_low)
        # Failed reversals override prior tags — they are the actionable signal
        result.loc[mask_failed_2u, 'strat_combo'] = 'Failed_2U'
        result.loc[mask_failed_2d, 'strat_combo'] = 'Failed_2D'

        # --- Continuation combos ---

        # 2U-1-2U Continuation (Bullish)
        mask_cont_bull = (prev2 == '2U') & (prev1 == '1') & (df['High'] > one_bar_high)
        # Only mark as continuation if not already marked as reversal
        cont_bull_only = mask_cont_bull & (result['strat_combo'] == 'none')
        result.loc[cont_bull_only, 'strat_combo'] = '2U-1-2U_continuation'

        # 2D-1-2D Continuation (Bearish)
        mask_cont_bear = (prev2 == '2D') & (prev1 == '1') & (df['Low'] < one_bar_low)
        cont_bear_only = mask_cont_bear & (result['strat_combo'] == 'none')
        result.loc[cont_bear_only, 'strat_combo'] = '2D-1-2D_continuation'

        # Simple two-bar continuations (used in community recaps as plain
        # "2U continuation" / "2D continuation" — distinct from the 3-bar
        # variants above which require a compressed inside bar between).
        mask_22u = (prev1 == '2U') & (labels == '2U')
        mask_22d = (prev1 == '2D') & (labels == '2D')
        result.loc[mask_22u & (result['strat_combo'] == 'none'), 'strat_combo'] = '2U_continuation'
        result.loc[mask_22d & (result['strat_combo'] == 'none'), 'strat_combo'] = '2D_continuation'

        # --- 3-bar exhaustion / reversal ---

        # 3-2 Reversal: outside bar followed by directional bar opposite to close
        prev1_bullish_close = close.shift(1) > df['Open'].shift(1) if 'Open' in df.columns else pd.Series(False, index=df.index)
        mask_3_rev_bear = (prev1 == '3') & prev1_bullish_close & (labels == '2D')
        mask_3_rev_bull = (prev1 == '3') & (~prev1_bullish_close) & (labels == '2U')
        result.loc[mask_3_rev_bear & (result['strat_combo'] == 'none'), 'strat_combo'] = '3-2D_reversal'
        result.loc[mask_3_rev_bull & (result['strat_combo'] == 'none'), 'strat_combo'] = '3-2U_reversal'

        # --- Setup detection (inside bar forming after directional bar) ---
        result['strat_setup'] = (labels == '1') & (prev1.isin(['2U', '2D', '3']))

        # --- Consecutive inside bars (compression) ---
        result['consecutive_1s'] = (labels == '1').astype(int).rolling(window=2, min_periods=1).sum()

        return result

    # -----------------------------------------------------------------------
    # Full Timeframe Continuity (FTFC)
    # -----------------------------------------------------------------------

    def calculate_ftfc(
        self,
        tf_dataframes: Dict[str, pd.DataFrame],
        weights: Dict[str, float] = None,
    ) -> Tuple[float, str, Dict[str, str]]:
        """Calculate FTFC alignment score from multiple timeframes.

        Parameters
        ----------
        tf_dataframes : dict mapping timeframe label -> OHLCV DataFrame
            Each DataFrame should have enough bars for classification.
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
            # Type 1 and 3 contribute 0 (neutral)

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
    # Signal integration bonus
    # -----------------------------------------------------------------------

    def get_strat_bonus(
        self,
        signal_direction: str,
        combo: str,
        ftfc_score: float,
        ftfc_threshold: float = None,
        orb_trend: int = 0,
    ) -> int:
        """Calculate bonus points for combined scoring.

        Parameters
        ----------
        signal_direction : 'CALL' or 'PUT'
        combo : strat combo label from detect_combos()
        ftfc_score : -1.0 to +1.0 from calculate_ftfc()
        ftfc_threshold : minimum absolute FTFC score for bonus
            (defaults to config.ftfc_threshold)
        orb_trend : ORB trend direction (1=bullish, -1=bearish, 0=neutral)

        Returns
        -------
        bonus : 0 to 3 (or negative if FTFC strongly contradicts)
        """
        if ftfc_threshold is None:
            ftfc_threshold = self.config.ftfc_threshold

        combo_bonus = self.config.combo_bonus
        ftfc_bonus = self.config.ftfc_bonus
        orb_alignment_bonus = self.config.orb_alignment_bonus

        bonus = 0

        # +combo_bonus for aligned Strat combo
        # Failed_2U is a bearish reversal signal (rejected breakout) → favors PUT.
        # Failed_2D is a bullish reversal signal (rejected breakdown) → favors CALL.
        # Plain 2U/2D continuations align with their direction.
        if signal_direction == 'CALL' and combo in (
            '2D-1-2U_reversal', '3-1-2U_reversal', '3-2U_reversal',
            '2U-1-2U_continuation', '2U_continuation',
            'Failed_2D',
        ):
            bonus += combo_bonus
        elif signal_direction == 'PUT' and combo in (
            '2U-1-2D_reversal', '3-1-2D_reversal', '3-2D_reversal',
            '2D-1-2D_continuation', '2D_continuation',
            'Failed_2U',
        ):
            bonus += combo_bonus

        # +ftfc_bonus for FTFC alignment (or -ftfc_bonus for strong contradiction)
        if signal_direction == 'CALL':
            if ftfc_score >= ftfc_threshold:
                bonus += ftfc_bonus
            elif ftfc_score <= -ftfc_threshold:
                bonus -= ftfc_bonus  # FTFC contradicts -- penalty
        elif signal_direction == 'PUT':
            if ftfc_score <= -ftfc_threshold:
                bonus += ftfc_bonus
            elif ftfc_score >= ftfc_threshold:
                bonus -= ftfc_bonus

        # +orb_alignment_bonus for ORB alignment
        if signal_direction == 'CALL' and orb_trend == 1:
            bonus += orb_alignment_bonus
        elif signal_direction == 'PUT' and orb_trend == -1:
            bonus += orb_alignment_bonus

        return bonus

    # -----------------------------------------------------------------------
    # Convenience: classify and add Strat columns to a DataFrame
    # -----------------------------------------------------------------------

    def add_strat_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Classify candles and detect combos, returning the original
        DataFrame with Strat columns appended.
        """
        labels = self.classify_series(df)
        combos = self.detect_combos(df, labels)
        return pd.concat([df, combos], axis=1)
