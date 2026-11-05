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
from functools import lru_cache
from typing import Any, Dict, Tuple, Optional

from lib.config import StratConfig
from lib.eastern_time import ET_NAME, eastern_now, session_schedule


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


def _numeric_prices(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Malformed price values become NaN and are explicitly classified invalid."""
    # Shallow copy without attrs: the result never carried them, and pandas
    # would otherwise deep-copy them on every column access below.
    bare = df.copy(deep=False)
    bare.attrs = {}
    prices = bare[columns].apply(pd.to_numeric, errors='coerce')
    return pd.DataFrame(prices.to_numpy(dtype=float, na_value=np.nan),
                        index=df.index, columns=columns)


def _valid_price_rows(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Validate the requested prices without removing observation positions."""
    prices = _numeric_prices(df, columns)
    valid = np.isfinite(prices).all(axis=1) & (prices['High'] >= prices['Low'])
    for column in ('Open', 'Close'):
        if column in columns:
            valid &= prices[column].between(prices['Low'], prices['High'])
    return valid


def validate_ohlc_rows(df: pd.DataFrame) -> pd.Series:
    """Finite, coherent full OHLC validity aligned to every input row.

    Missing columns are a caller error, not permission to invent prices.
    The range-only legacy classifier below has a deliberately narrower contract.
    """
    columns = ['Open', 'High', 'Low', 'Close']
    missing = [column for column in columns if column not in df]
    if missing:
        raise ValueError(f"missing OHLC columns: {', '.join(missing)}")
    return _valid_price_rows(df, columns)


def _gap_before(df: pd.DataFrame) -> pd.Series:
    """Discontinuities under an explicitly supplied cadence; never infer one.

    Source adapters own session-aware cadence/coverage. A caller supplying
    a fixed interval across a session boundary gets conservative unknown there.
    """
    gaps = pd.Series(False, index=df.index)
    supplied = df.attrs.get('gap_before_by_timestamp')
    if supplied is not None:
        def key(stamp):
            semantics = df.attrs.get('gap_key_semantics')
            if semantics == 'utc_instant':
                if stamp.tzinfo is None:
                    stamp = stamp.tz_localize(df.attrs['naive_index_timezone'],
                                              ambiguous='raise', nonexistent='raise')
                return stamp.tz_convert('UTC').isoformat()
            if semantics == 'session_label' and stamp.tzinfo is not None:
                stamp = stamp.tz_localize(None)  # tz-ok: preserve daily label identity
            return stamp.isoformat()
        return pd.Series([bool(supplied.get(key(stamp), True))
                          for stamp in df.index], index=df.index)
    interval = df.attrs.get('expected_interval')
    if interval is not None:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError('expected_interval requires a DatetimeIndex')
        interval = pd.Timedelta(interval)
        if interval <= pd.Timedelta(0):
            raise ValueError('expected_interval must be positive')
        gaps = df.index.to_series().diff().ne(interval)
        if len(gaps):
            gaps.iloc[0] = False
    return gaps


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

    def __init__(self, strat_config: StratConfig = None, *, rule_version: str = 'strat-state-v2'):
        if rule_version not in ('strat-state-v2', 'legacy-pattern-v1'):
            raise ValueError(f"unsupported Strat rule version: {rule_version}")
        self.rule_version = rule_version
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

        Returns '1', '2U', '2D', '3', or unknown 'X' for invalid ranges.
        This scalar API deliberately validates high/low only.
        """
        try:
            ranges = np.asarray((curr_high, curr_low, prev_high, prev_low), dtype=float)
        except (TypeError, ValueError):
            # Malformed scalar price, not a replacement observation.
            return 'X'
        if not np.isfinite(ranges).all():
            return 'X'
        curr_high, curr_low, prev_high, prev_low = ranges
        if curr_high < curr_low or prev_high < prev_low:
            return 'X'
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

        High/Low-only legacy inputs are supported. Every supplied Open/Close
        must also be finite and inside the range. Invalid rows and the row
        immediately after them stay 'X'; removing rows would bridge gaps.
        Explicit ``df.attrs['expected_interval']`` detects timestamp gaps.
        ``Last`` is the explicit legacy alias when ``Close`` is absent.
        """
        if 'Close' not in df and 'Last' in df:
            df = df.rename(columns={'Last': 'Close'})
        columns = [column for column in ('High', 'Low', 'Open', 'Close') if column in df]
        prices = _numeric_prices(df, columns)
        prev_high = prices['High'].shift(1)
        prev_low = prices['Low'].shift(1)
        curr_high = prices['High']
        curr_low = prices['Low']

        higher_high = curr_high > prev_high
        lower_low = curr_low < prev_low

        labels = pd.Series('X', index=df.index)
        labels[~higher_high & ~lower_low] = '1'
        labels[higher_high & ~lower_low] = '2U'
        labels[~higher_high & lower_low] = '2D'
        labels[higher_high & lower_low] = '3'

        valid = _valid_price_rows(prices, columns)
        adjacent = valid & valid.shift(1, fill_value=False) & ~_gap_before(df)
        labels.loc[~adjacent] = 'X'
        return labels

    # -----------------------------------------------------------------------
    # Trigger levels
    # -----------------------------------------------------------------------

    @staticmethod
    def get_trigger_levels(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Prior valid observation's H/L; invalid rows never become triggers."""
        if 'Close' not in df and 'Last' in df:
            df = df.rename(columns={'Last': 'Close'})
        columns = [column for column in ('High', 'Low', 'Open', 'Close') if column in df]
        prices = _numeric_prices(df, columns)
        valid = _valid_price_rows(prices, columns)
        return prices['High'].where(valid).shift(1), prices['Low'].where(valid).shift(1)

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
        - consecutive_1s: current consecutive inside-bar count
        - pattern_facts: all applicable labels in priority order
        - failed_2u / failed_2d: independent nullable flags (unknown if O/C absent)
        - candle_color / close_location: green/red/doji/unknown and (C-L)/(H-L)
        - close_source: Close, explicit legacy Last alias, or None if absent
        - pending_setup: alias for the inside-bar-pending strat_setup flag
        - gap_before: discontinuity under explicitly supplied expected_interval

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
        bar. Tests in `tests/lib/test_strat.py::TestSetupVsComboOrthogonality`
        lock this behaviour in.

        Priority order on collision (§3 of doc): higher-listed wins. Lower
        priorities only fill bars still tagged 'none'.
        Missing or unrecognized supplied labels remain unknown ('X').
        """
        if labels is None:
            labels = self.classify_series(df)
        else:
            # Reindexing can introduce nulls; normalize before masks so unknown
            # classifications cannot become known-false failure facts.
            labels = labels.reindex(df.index).astype(object)
            labels = labels.where(labels.isin(['X', '1', '2U', '2D', '3']), 'X')
            # Supplied labels cannot bypass valid-price/adjacency guards.
            labels = labels.where(self.classify_series(df) != 'X', 'X')

        prev1 = labels.shift(1)
        prev2 = labels.shift(2)

        trigger_high, trigger_low = self.get_trigger_levels(df)
        # Missing O/C is explicitly unavailable: never synthesize a clean bar.
        close_source = 'Close' if 'Close' in df else ('Last' if 'Last' in df else None)
        close = (_numeric_prices(df, [close_source])[close_source]
                 if close_source is not None else pd.Series(np.nan, index=df.index))
        open_ = (_numeric_prices(df, ['Open'])['Open']
                 if 'Open' in df else pd.Series(np.nan, index=df.index))

        result = pd.DataFrame(index=df.index)
        result['strat_candle'] = labels
        result['strat_combo'] = 'none'
        result['strat_setup'] = False
        result['trigger_high'] = trigger_high
        result['trigger_low'] = trigger_low

        none = lambda: result['strat_combo'] == 'none'

        # Legacy trained inputs keep their valid-bar breakout masks explicitly.
        # Both versions use the same invalid/gap guards above.
        legacy = self.rule_version == 'legacy-pattern-v1'
        ranges = _numeric_prices(df, ['High', 'Low']) if legacy else None
        breaks_up = ((ranges['High'] > ranges['High'].shift(1)) & labels.ne('X')
                     if legacy else labels.eq('2U'))
        breaks_down = ((ranges['Low'] < ranges['Low'].shift(1)) & labels.ne('X')
                       if legacy else labels.eq('2D'))

        # ── Priority 1: 3-bar reversals (X-1-2) ────────────────────────────
        mask_212_bull = (prev2 == '2D') & (prev1 == '1') & breaks_up
        mask_212_bear = (prev2 == '2U') & (prev1 == '1') & breaks_down
        result.loc[mask_212_bull & none(), 'strat_combo'] = '212_bull_reversal'
        result.loc[mask_212_bear & none(), 'strat_combo'] = '212_bear_reversal'

        # ── Priority 2: 312 reversals (3-1-2) ──────────────────────────────
        mask_312_bull = (prev2 == '3') & (prev1 == '1') & breaks_up
        mask_312_bear = (prev2 == '3') & (prev1 == '1') & breaks_down
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
        mask_212_bull_cont = (prev2 == '2U') & (prev1 == '1') & breaks_up
        mask_212_bear_cont = (prev2 == '2D') & (prev1 == '1') & breaks_down
        result.loc[mask_212_bull_cont & none(), 'strat_combo'] = '212_bull_continuation'
        result.loc[mask_212_bear_cont & none(), 'strat_combo'] = '212_bear_continuation'

        # ── Priority 6: 32 reversals (3 followed by directional 2) ─────────
        # Methodology §9: outside-bar color imposes no extra condition.
        mask_32_bear = (prev1 == '3') & (labels == '2D')
        mask_32_bull = (prev1 == '3') & (labels == '2U')
        if legacy:
            prior_color_known = np.isfinite(close.shift(1)) & np.isfinite(open_.shift(1))
            mask_32_bear &= prior_color_known & (close.shift(1) > open_.shift(1))
            mask_32_bull &= prior_color_known & (close.shift(1) <= open_.shift(1))
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
        result['pending_setup'] = result['strat_setup']
        inside = labels == '1'
        if legacy:
            # Persisted legacy feature tables carry the two-bar rolling sum;
            # changing it would silently rewrite their historical values.
            result['consecutive_1s'] = inside.astype(int).rolling(window=2, min_periods=1).sum()
        else:
            result['consecutive_1s'] = inside.astype(int).groupby((~inside).cumsum()).cumsum()

        # Capture masks BEFORE priority filtering so collisions retain every fact.
        patterns = [
            ('212_bull_reversal', mask_212_bull), ('212_bear_reversal', mask_212_bear),
            ('312_bull_reversal', mask_312_bull), ('312_bear_reversal', mask_312_bear),
            ('132_bull_continuation', mask_132_bull), ('132_bear_continuation', mask_132_bear),
            ('322_bull_continuation', mask_322_bull), ('322_bear_continuation', mask_322_bear),
            ('212_bull_continuation', mask_212_bull_cont), ('212_bear_continuation', mask_212_bear_cont),
            ('32_bull_reversal', mask_32_bull), ('32_bear_reversal', mask_32_bear),
            ('22_bull_reversal', mask_22_bull_rev), ('22_bear_reversal', mask_22_bear_rev),
            ('22_bull_continuation', mask_22_bull), ('22_bear_continuation', mask_22_bear),
            ('131_setup', mask_131), ('111_inside_compression', mask_111),
            ('11_inside_compression', mask_11), ('f2u_bear_reversal', mask_f2u),
            ('f2d_bull_reversal', mask_f2d), ('clean_2u_bull', mask_clean_2u),
            ('clean_2d_bear', mask_clean_2d),
        ]
        result['pattern_facts'] = [
            [name for (name, _), applies in zip(patterns, row) if applies]
            for row in zip(*(mask.to_numpy() for _, mask in patterns))
        ]
        price_frame = df.rename(columns={'Last': 'Close'}) if close_source == 'Last' else df
        price_valid = _valid_price_rows(price_frame, [
            c for c in ('High', 'Low', 'Open', 'Close') if c in price_frame])
        color_available = price_valid & np.isfinite(open_) & np.isfinite(close)
        failure_available = color_available & (labels != 'X')
        result['failed_2u'] = mask_f2u.astype('boolean').where(failure_available)
        result['failed_2d'] = mask_f2d.astype('boolean').where(failure_available)
        result['candle_color'] = np.select(
            [color_available & (close > open_), color_available & (close < open_), color_available],
            ['green', 'red', 'doji'], default='unknown',
        )
        ranges = _numeric_prices(df, ['High', 'Low'])
        width = ranges['High'] - ranges['Low']
        result['close_location'] = ((close - ranges['Low']) / width.where(width > 0)).where(
            price_valid & np.isfinite(close))
        result['gap_before'] = _gap_before(df)
        result['close_source'] = close_source
        result.attrs['strat_rule_version'] = self.rule_version

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

    def describe_weighted_candle_alignment(
        self, tf_dataframes: Dict[str, pd.DataFrame], weights: Dict[str, float] = None,
    ) -> Dict[str, Any]:
        """Inspect the unchanged legacy vote; exact weight keys are intentional.

        Unknown candle classes contribute zero numerator but retain their weight
        in the denominator, exactly as calculate_ftfc historically specified.
        Aliases are annotated here, never merged or used to rewrite weights.
        """
        weights = dict(self._default_weights if weights is None else weights)
        score, direction, labels = self.calculate_ftfc(tf_dataframes, weights)
        frames = {}
        for tf in dict.fromkeys([*weights, *tf_dataframes]):
            label = labels.get(tf)
            weight = weights.get(tf, 0.0)
            frames[tf] = {
                'canonical_timeframe': _canonical_timeframe(tf), 'label': label,
                'weight': weight, 'included_in_denominator': label is not None,
                'weighted_contribution': (weight if label == '2U' else
                                          -weight if label == '2D' else 0.0)
                                         if label is not None else None,
                'reasons': ['missing_or_insufficient_bars'] if label is None else
                           ['unknown_candle'] if label == 'X' else [],
            }
        denominator = sum(weights.get(tf, 0.0) for tf in labels)
        return {
            'version': 'legacy-candle-v1', 'score': score, 'direction': direction,
            'available': denominator != 0, 'weights': weights, 'denominator': denominator,
            'direction_threshold': self.config.ftfc_direction_threshold,
            'labels': labels, 'frames': frames,
            'contributing_frames': [tf for tf in labels if weights.get(tf, 0.0) != 0],
            'zero_weight_frames': [tf for tf in labels if weights.get(tf, 0.0) == 0],
            'missing_frames': [tf for tf in frames if tf not in labels],
        }

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
        return pd.concat([df.drop(columns=df.columns.intersection(combos.columns)), combos], axis=1)


# Explicit aliases for strict evidence identity. Legacy weight keys stay untouched.
_TIMEFRAME_ALIASES = {
    'D': '1d', '1D': '1d', 'daily': '1d',
    'W': '1w', '1W': '1w', 'weekly': '1w',
    'M': '1mo', '1M': '1mo', 'monthly': '1mo',
    'Q': '1q', '1Q': '1q', 'quarterly': '1q',
    'Y': '1y', '1Y': '1y', 'yearly': '1y', '60m': '1h',
}


def _canonical_timeframe(timeframe: str) -> str:
    return _TIMEFRAME_ALIASES.get(timeframe, timeframe)


def _finite_scalar(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _required_frames(tf_dataframes, required_timeframes):
    """Reject ambiguous identity instead of silently merging alias observations."""
    frames = {}
    for name, frame in tf_dataframes.items():
        canonical = _canonical_timeframe(name)
        if canonical in frames:
            raise ValueError(f'duplicate timeframe alias: {name} -> {canonical}')
        frames[canonical] = (name, frame)
    required = [_canonical_timeframe(name) for name in required_timeframes]
    if len(set(required)) != len(required):
        raise ValueError('duplicate required timeframe alias')
    return frames, required


def _strict_evidence(frame):
    """Read adapter-declared current coverage, never an older retained row's open.

    This is arithmetic evidence, not a freshness or adjusted-price certification.
    A partial period is usable if all observations due so far are accounted for.
    Unknown acquisition/basis metadata remains unknown in the returned coverage.
    """
    if frame is None:
        return {}, ['missing_frame']
    coverage = dict(frame.attrs.get('coverage', {}))
    if 'open' in coverage:
        coverage['open'] = _finite_scalar(coverage['open'])
    reasons = list(coverage.get('reasons', []))
    if (frame.attrs.get('aggregation_policy') != 'observed_v2' or
            coverage.get('aggregation_policy') != 'observed_v2'):
        reasons.append('unsupported_aggregation_policy')
    if coverage.get('available') is not True:
        reasons.append('unavailable_coverage')
    if coverage.get('coverage_complete') is not True:
        reasons.append('incomplete_coverage')
    if coverage.get('session_policy') != 'NYSE_regular':
        reasons.append('unknown_session_policy')
    if coverage.get('source_resolution') in (None, 'unknown'):
        reasons.append('unknown_source_resolution')
    if coverage.get('timestamp_semantics') not in ('session_label', 'bar_start'):
        reasons.append('unsupported_timestamp_semantics')
    if not coverage.get('source_cutoff'):
        reasons.append('unknown_source_cutoff')
    return coverage, list(dict.fromkeys(reasons))


def _continuity_result(version, required, frames, reasons, directions):
    if not required:
        reasons.append('empty_required_timeframes')
    if any(not record['available'] for record in frames.values()):
        reasons.append('unavailable_required_frames')
    available = not reasons
    direction = ('bullish' if all(value == 'bullish' for value in directions) else
                 'bearish' if all(value == 'bearish' for value in directions) else 'mixed') if available else 'unavailable'
    return {'version': version, 'required_timeframes': required, 'frames': frames,
            'available': available, 'direction': direction,
            'full_continuity': available and direction in ('bullish', 'bearish'),
            'reasons': reasons, 'freshness_policy': 'unknown'}


def calculate_timeframe_continuity(
    tf_dataframes: dict[str, pd.DataFrame], observed_price: float,
    required_timeframes: list[str],
) -> dict:
    """Compare ONE finite observed price to every explicitly required current open.

    Inputs must already share a coherent declared price basis/observation context.
    This pure helper does not acquire a quote, adjust prices, infer freshness or
    substitute a previous period. Provenance remains inspectable in coverage.
    """
    inputs, required = _required_frames(tf_dataframes, required_timeframes)
    price = _finite_scalar(observed_price)
    reasons = ['invalid_observed_price'] if price is None else []
    frames, directions = {}, []
    for tf in required:
        name, frame = inputs.get(tf, (None, None))
        coverage, missing = _strict_evidence(frame)
        open_ = _finite_scalar(coverage.get('open'))
        if coverage.get('period_open_observed') is not True:
            missing.append('missing_period_open')
            open_ = None
        elif open_ is None:
            missing.append('invalid_period_open')
        if price is None:
            missing.append('invalid_observed_price')
        relation = ('above' if price > open_ else 'below' if price < open_ else
                    'at_open') if not missing else 'unavailable'
        frames[tf] = {'input_timeframe': name, 'available': not missing, 'open': open_,
                      'relation': relation, 'coverage': coverage, 'reasons': missing}
        directions.append({'above':'bullish','below':'bearish'}.get(relation, 'mixed'))
    result = _continuity_result('price-open-v1', required, frames, reasons, directions)
    result['observed_price'] = price
    result['price_provenance'] = 'caller_supplied' if price is not None else 'unknown'
    return result


def calculate_directional_candle_continuity(
    tf_dataframes: dict[str, pd.DataFrame], required_timeframes: list[str],
) -> dict:
    """Strict current-period directional classes, independent of color/weights.

    Inside/outside are known non-unanimous evidence; X is unavailable. The
    coverage retains partial/completed status for evolving higher periods.
    """
    inputs, required = _required_frames(tf_dataframes, required_timeframes)
    frames, directions = {}, []
    classifier = StratClassifier()
    for tf in required:
        name, frame = inputs.get(tf, (None, None))
        coverage, missing = _strict_evidence(frame)
        label = 'X'
        if frame is not None and len(frame) and not missing:
            if not all(column in frame for column in ('Open', 'High', 'Low', 'Close')):
                missing.append('missing_ohlc_columns')
            semantics = frame.attrs.get('period_key_semantics')
            if (not isinstance(frame.index, pd.DatetimeIndex) or
                    semantics not in ('utc_instant', 'session_label') or
                    (semantics == 'utc_instant' and frame.index.tz is None and
                     not frame.attrs.get('naive_index_timezone'))):
                missing.append('unknown_period_index')
        if frame is not None and len(frame) and not missing:
            stamp = frame.index[-1]
            if frame.attrs.get('period_key_semantics') == 'utc_instant':
                if stamp.tzinfo is None:
                    stamp = stamp.tz_localize(frame.attrs['naive_index_timezone'])
                stamp = stamp.tz_convert('UTC')
            elif stamp.tzinfo is not None:
                stamp = stamp.tz_localize(None)  # tz-ok: period label identity
            record = frame.attrs.get('period_coverage', {}).get(stamp.isoformat(), {})
            if (not record or not coverage.get('period_start') or
                    any(record.get(key) != coverage.get(key) for key in ('period_start', 'period_end'))):
                missing.append('missing_current_period_candle')
            elif not missing:
                label = classifier.classify_series(frame).iloc[-1]
        if label == 'X':
            missing.append('unknown_candle')
        frames[tf] = {'input_timeframe': name, 'available': not missing, 'label': label,
                      'coverage': coverage, 'reasons': missing}
        directions.append({'2U':'bullish','2D':'bearish'}.get(label, 'mixed'))
    return _continuity_result('directional-candle-v1', required, frames, [], directions)


# ---------------------------------------------------------------------------
# Single source of truth for per-ticker live Strat + FTFC status.
#
# Both the 8:30 AM premarket-brief (gcp/premarket_brief.py) and the LLM
# pipeline analyst (lib/agents/summarizers.summarize_strat_status) call
# this helper instead of duplicating the daily-bars-to-FTFC composition.
# ---------------------------------------------------------------------------


def finite_snapshot(value):
    """JSON boundary: missing/nonfinite numbers stay null, never neutral facts."""
    if isinstance(value, dict):
        return {str(key): finite_snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_snapshot(item) for item in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


# ---------------------------------------------------------------------------
# Closed-candle confirmation (owner rule): a signal/setup is confirmed only
# after its selected candle has closed at the observation clock.
# ---------------------------------------------------------------------------

CONFIRMATION_TIMEFRAMES: Tuple[str, ...] = ('5m', '15m', '30m', '1h', '4h', '1w')
CONFIRMATION_RULE_VERSION = 'closed-candle-v1'


def _period_bounds(timeframe: str, clock: pd.Timestamp):
    """Expected periods near ``clock`` under the observed_v2 conventions.

    Intraday buckets anchor at the session open and clip at the close; weekly
    periods end at the week's last actual session close. Returns
    ``[(start, end, nominal)]`` in Eastern, oldest first.
    """
    from lib.data_loader import RESAMPLE_RULES

    lookback = 21 if timeframe == '1w' else 7
    last_day = clock.date()
    if timeframe == '1w':
        # The current week ends at its last actual session close, which can be
        # after the clock's date: without it, Monday's close reads as a closed
        # week and hides the week that really closed (Codex r4476732518).
        last_day = pd.Timestamp(last_day).to_period('W-FRI').end_time.date()
    schedule = session_schedule(clock.date() - pd.Timedelta(days=lookback), last_day)
    periods = []
    if timeframe == '1w':
        weeks = {}
        for label, row in schedule.iterrows():
            week = pd.Timestamp(label).to_period('W-FRI')
            weeks.setdefault(week, []).append(row)
        for week in sorted(weeks):
            rows = weeks[week]
            periods.append((rows[0]['market_open'].tz_convert(ET_NAME),
                            rows[-1]['market_close'].tz_convert(ET_NAME), True))
        return periods
    interval = pd.Timedelta(RESAMPLE_RULES[timeframe])
    for row in schedule.itertuples():
        start = row.market_open.tz_convert(ET_NAME)
        close = row.market_close.tz_convert(ET_NAME)
        while start < close:
            end = min(start + interval, close)
            periods.append((start, end, end - start == interval))
            start = start + interval
    return periods


def _coverage_key(stamp, timeframe: str) -> str:
    stamp = pd.Timestamp(stamp)
    if timeframe == '1w':
        if stamp.tzinfo is not None:
            stamp = stamp.tz_localize(None)  # tz-ok: weekly session label identity
        return stamp.isoformat()
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(ET_NAME, ambiguous='raise', nonexistent='raise')
    return stamp.tz_convert('UTC').isoformat()


def _unconfirmed(timeframe, reasons, **extra):
    return {'timeframe': timeframe, 'state': 'unavailable', 'confirmed': False,
            'reasons': list(dict.fromkeys(reasons)), 'candle': None, 'combo': None,
            'setup': False, 'period_start': None, 'period_end': None,
            'developing': None, **extra}


def _confirm_timeframe(frame: pd.DataFrame, timeframe: str, clock: pd.Timestamp,
                       strat: 'StratClassifier') -> Dict[str, Any]:
    periods = _period_bounds(timeframe, clock)
    closed = [period for period in periods if period[1] <= clock]
    current = next((period for period in periods if period[0] <= clock < period[1]), None)
    developing = None
    if current is not None:
        developing = {'state': 'developing', 'confirmed': False,
                      'period_start': current[0].isoformat(),
                      'period_end': current[1].isoformat(),
                      'reasons': ['developing_candle']}
    if not closed:
        return _unconfirmed(timeframe, ['unresolved_anchor'], developing=developing)
    expected = closed[-1]
    coverage = frame.attrs.get('period_coverage', {})
    keys = [_coverage_key(stamp, timeframe) for stamp in frame.index]
    completed = [position for position, key in enumerate(keys)
                 if coverage.get(key, {}).get('completed') is True]
    if not completed:
        return _unconfirmed(timeframe, ['no_completed_bar'], developing=developing)
    bars = frame.iloc[completed].copy()
    bars.attrs = dict(frame.attrs)
    record = coverage[keys[completed[-1]]]
    start = pd.Timestamp(record['period_start']) if record.get('period_start') else None
    end = pd.Timestamp(record['period_end']) if record.get('period_end') else None
    reasons = []
    if start is None or end is None:
        reasons.append('unresolved_anchor')
    elif start != expected[0] or end != expected[1]:
        # The newest closed period has no aggregated bar: never let an older
        # bar stand in for it.
        reasons.append('latest_closed_period_missing')
    elif not expected[2]:
        reasons.append('shorter_session_bucket_unapproved')
    if not record.get('coverage_complete'):
        reasons.append('incomplete_coverage')
    if not record.get('available'):
        reasons.append('unavailable_bar')
    reasons.extend(record.get('reasons', []))
    labels = strat.classify_series(bars)
    combos = strat.detect_combos(bars, labels)
    candle = str(labels.iloc[-1])
    combo = str(combos['strat_combo'].iloc[-1])
    setup = bool(combos['strat_setup'].iloc[-1])
    if candle == 'X':
        reasons.append('unavailable_classification')
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        state = 'unconfirmed'
    elif combo != 'none' or setup:
        state = 'confirmed'
    else:
        state = 'none'
    return {'timeframe': timeframe, 'state': state, 'confirmed': state == 'confirmed',
            'reasons': reasons, 'candle': None if candle == 'X' else candle,
            'combo': combo if candle != 'X' else None, 'setup': setup and candle != 'X',
            'period_start': record.get('period_start'), 'period_end': record.get('period_end'),
            'source_cutoff': record.get('source_cutoff'), 'developing': developing}


def compute_confirmed_setups(
    *,
    observation_ts,
    intraday_df: Optional[pd.DataFrame] = None,
    daily_df: Optional[pd.DataFrame] = None,
    timeframes: Optional[list] = None,
    strat_config: Optional[StratConfig] = None,
) -> Dict[str, Any]:
    """Closed-candle setups on 5m/15m/30m/1h/4h (intraday) and 1w (daily).

    The source is cut at ``observation_ts`` before aggregation (observed_v2),
    so later rows cannot change the result. Only the newest closed period of
    each timeframe can confirm; the developing period is reported separately
    and never confirms. Missing sources, missing/invalid observations, gaps,
    an unresolved anchor and the shorter final 4h bucket (owner decision
    pending) stay unconfirmed with reasons. No equality, 312, PMG, stop or
    expiry policy is selected here.
    """
    from lib.data_loader import DataLoader, _observation_clock

    if observation_ts is None:
        raise ValueError('compute_confirmed_setups requires an explicit observation clock')
    clock = _observation_clock(observation_ts)
    loader = DataLoader()
    strat = StratClassifier(strat_config=strat_config)
    results = {}
    for timeframe in timeframes or CONFIRMATION_TIMEFRAMES:
        if timeframe not in CONFIRMATION_TIMEFRAMES:
            raise ValueError(f'{timeframe} is not a confirmation timeframe')
        source = daily_df if timeframe == '1w' else intraday_df
        if source is None:
            results[timeframe] = _unconfirmed(timeframe, ['source_not_supplied'])
            continue
        frame = loader.aggregate_to_timeframe(source, timeframe, observation_ts=clock,
                                              aggregation_policy='observed_v2')
        source_reasons = frame.attrs.get('coverage', {}).get('reasons', [])
        if frame.empty:
            results[timeframe] = _unconfirmed(timeframe, source_reasons or ['no_observations'])
            continue
        results[timeframe] = _confirm_timeframe(frame, timeframe, clock, strat)
    return {
        'rule_version': CONFIRMATION_RULE_VERSION,
        'observation_ts': clock.isoformat(),
        'timeframes': results,
        'confirmed': [tf for tf, result in results.items() if result['confirmed']],
    }


def compute_strat_status(
    ticker: str,
    df: Optional[pd.DataFrame] = None,
    as_of: Optional[date_type] = None,
    timeframes: Optional[list[str]] = None,
    strat_config: Optional[StratConfig] = None,
    inclusive_today: bool = True,
    intraday_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Snapshot at one Eastern observation clock, preserving legacy daily votes.

    ``confirmed_setups`` applies the closed-candle rule at the same clock:
    1w from the daily source and 5m-4h only from an explicitly supplied
    ``intraday_df`` (otherwise ``source_not_supplied``).

    A plain date (or YYYY-MM-DD string) with inclusive_today=True explicitly
    means end of that date. Datetime values are instants; naive datetime values
    are Eastern wall time. Live None resolves eastern_now(), never an unlimited
    cutoff. inclusive_today=False always excludes the observation session's
    daily row, including after its close. Daily indexes are exchange labels.

    Coverage records describe the CURRENT requested periods, independently of
    the last completed daily candle. Missing or malformed completed observations
    remain explicit; they cannot be replaced by an older apparently fresh bar.
    """
    from datetime import datetime
    from lib.data_loader import DataLoader, _observation_clock, _session_labels

    timeframes = timeframes or ['1d', '1w', '1mo']
    date_only = (isinstance(as_of, date_type) and not isinstance(as_of, datetime) or
                 isinstance(as_of, str) and len(as_of) == 10)
    clock_value = eastern_now() if as_of is None else as_of
    if date_only:
        clock_value = pd.Timestamp(as_of) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    clock = _observation_clock(clock_value)
    confirmation_clock = clock
    if not inclusive_today:
        # Every input excludes the observation session's own bars, so closed-
        # candle confirmation stops before that session opens too: otherwise a
        # date-only replay confirms a week that closed later that day
        # (Codex r4480286394).
        today = session_schedule(clock.date(), clock.date())
        if len(today):
            confirmation_clock = min(clock, today.iloc[0]['market_open'].tz_convert(ET_NAME)
                                     - pd.Timedelta(microseconds=1))
    loader = DataLoader()
    if df is None:
        df = loader.load_daily(ticker)
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    if 'Close' not in df and 'Last' in df:
        # The legacy close alias the classifier and adapters accept (Codex r4481033971).
        df = df.rename(columns={'Last': 'Close'})
    contract_keys = ('source_resolution', 'session_policy', 'timestamp_semantics')
    if not any(key in df.attrs for key in contract_keys):
        # The legacy call shape explicitly supplies daily session-label data.
        # Only genuinely unannotated inputs receive this compatibility default.
        df.attrs.update(source_resolution='1d', session_policy='NYSE_regular',
                        timestamp_semantics='session_label')
    confirmation_source = df.copy()
    source_reasons = list(df.attrs.get('source_contract_reasons', []))
    if df.attrs.get('source_resolution') not in ('1d', '1D', 'daily'):
        source_reasons.append('unsupported_daily_source_resolution')
    if df.attrs.get('session_policy') != 'NYSE_regular':
        source_reasons.append('unknown_session_policy')
    if df.attrs.get('timestamp_semantics') != 'session_label':
        source_reasons.append('unsupported_timestamp_semantics')
    if source_reasons:
        df = df.iloc[:0]
    df.index = _session_labels(df.index)
    df = df.sort_index()
    if len(df):
        schedule = session_schedule(df.index.min().date(), df.index.max().date())
        closes = schedule['market_close'].reindex(df.index)
        eligible = closes.notna() & (closes <= clock)
        if not inclusive_today:
            eligible &= df.index.date < clock.date()
        df = df.loc[eligible.to_numpy()]
    # Coverage and FTFC stop at the same cutoff as confirmation, so a date-only
    # replay that excludes the day does not expect its candle (Codex r4481033962).
    tf_dfs = loader.build_multi_timeframe(df, timeframes=timeframes,
                                          observation_ts=confirmation_clock,
                                          aggregation_policy='observed_v2')
    coverage = {tf: frame.attrs['coverage'] for tf, frame in tf_dfs.items()}
    for record in coverage.values():
        record['reasons'] = list(dict.fromkeys(source_reasons + record['reasons']))
    daily = loader.aggregate_to_timeframe(df, '1d', observation_ts=confirmation_clock,
                                          aggregation_policy='observed_v2')
    # Session adjacency supplied by the adapter must also guard daily combos.
    df.attrs['gap_before_by_timestamp'] = daily.attrs['gap_before_by_timestamp']
    df.attrs['gap_key_semantics'] = 'session_label'
    data_as_of = None
    if len(df):
        data_as_of = session_schedule(df.index[-1].date(), df.index[-1].date()).iloc[-1][
            'market_close'].tz_convert(ET_NAME).isoformat()
    valid = validate_ohlc_rows(df) if len(df) else pd.Series(dtype=bool)
    validity_reasons = (source_reasons if source_reasons else
                        [] if len(valid) and valid.iloc[-1] else
                        ['invalid_ohlc' if len(df) else 'no_observations'])
    metadata = {
        'ticker': ticker.upper(), 'rule_version': 'strat-state-v2',
        'aggregation_policy': 'observed_v2',
        'observation_ts': clock.isoformat(), 'session': str(clock.date()),
        'clock_policy': 'date_only_eod' if date_only else 'observation_instant',
        'data_as_of': data_as_of, 'coverage': coverage,
        'price_adjustment': df.attrs.get('price_adjustment', 'unknown'),
        'source_acquired_at': df.attrs.get('source_acquired_at'),
        'source_acquisition_status': df.attrs.get('source_acquisition_status', 'unknown'),
        'bar_validity': {'valid': bool(len(valid) and valid.iloc[-1]),
                         'reasons': validity_reasons},
        'confirmed_setups': compute_confirmed_setups(
            observation_ts=confirmation_clock, intraday_df=intraday_df,
            daily_df=confirmation_source, strat_config=strat_config),
    }
    strat = StratClassifier(strat_config=strat_config)
    metadata.update(
        timeframe_continuity=calculate_timeframe_continuity(tf_dfs, None, timeframes),
        directional_candle_continuity=calculate_directional_candle_continuity(tf_dfs, timeframes),
        weighted_candle_alignment=strat.describe_weighted_candle_alignment(tf_dfs),
    )
    if source_reasons:
        return {**metadata, 'available': False, 'reason': 'unsupported_source_contract',
                'date': '', 'last_candle': 'X'}
    if len(df) < 2:
        return {**metadata, 'available': False, 'reason': f'insufficient bars for {ticker}',
                'date': str(df.index[-1].date()) if len(df) else '', 'last_candle': 'X'}
    if not valid.iloc[-1]:
        return {**metadata, 'available': False, 'reason': 'invalid_ohlc',
                'date': str(df.index[-1].date()), 'last_candle': 'X'}

    # Daily candle + combo from the latest bar
    labels = strat.classify_series(df)
    if labels.iloc[-1] == 'X':
        reasons = metadata['bar_validity']['reasons']
        if not valid.iloc[-2]:
            reasons.append('invalid_previous_ohlc')
        if _gap_before(df).iloc[-1]:
            reasons.append('missing_previous_observation')
        return {**metadata, 'available': False, 'reason': 'unavailable_classification',
                'date': str(df.index[-1].date()), 'last_candle': 'X'}
    combos = strat.detect_combos(df, labels)
    last_candle = labels.iloc[-1]
    last_combo = combos['strat_combo'].iloc[-1] if 'strat_combo' in combos.columns else None
    last_setup = combos['strat_setup'].iloc[-1] if 'strat_setup' in combos.columns else False

    # Multi-timeframe FTFC via the same loader.build_multi_timeframe path
    # the brief uses, so D/W/M classifications stay byte-identical.
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
        **metadata,
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
# Powers "given all the bars, classify every completed bar and describe the
# in-progress (upcoming) period's break setup" across daily/weekly/monthly/
# quarterly. Pure pandas — deterministic, hermetically testable.
# ---------------------------------------------------------------------------

STRAT_HISTORY_TIMEFRAMES: list[str] = ['1d', '1w', '1mo', '1q']


def _derive_strat_flags(combo: str, candle: str) -> Dict[str, bool]:
    """Continuation/reversal/inside/setup flags from a combo label + candle."""
    c = combo or 'none'
    return {
        "is_continuation": "continuation" in c,
        "is_reversal": "reversal" in c,
        "is_inside": candle == '1',
        "is_setup": candle == '1',
    }


def _last_directional(labels: pd.Series) -> Optional[str]:
    """Most recent directional label without crossing unknown observation state."""
    for lab in reversed(list(labels)):
        if lab == 'X':
            return None
        if lab in ('2U', '2D'):
            return lab
    return None


def _upcoming_setup(tf_df: pd.DataFrame, labels: pd.Series,
                    combos: pd.DataFrame) -> Dict[str, Any]:
    """Describe the break setup for the NEXT bar of this timeframe.

    Trigger lines = latest completed bar's High/Low. Break above → '2U', below
    → '2D'; continuation vs reversal read against the most recent directional
    bar. The 50% line mirrors the detector's "50% Trigger".
    """
    last = tf_df.iloc[-1]
    last_candle = str(labels.iloc[-1])
    last_combo = str(combos['strat_combo'].iloc[-1])
    valid = bool(validate_ohlc_rows(tf_df.iloc[[-1]]).iloc[0])
    th = float(last['High']) if valid else None
    tl = float(last['Low']) if valid else None
    mid = (th + tl) / 2 if (th is not None and tl is not None) else None

    prior_dir = _last_directional(labels)
    if prior_dir == '2U':
        break_up, break_down = '2U continuation', '2D reversal'
    elif prior_dir == '2D':
        break_up, break_down = '2U reversal', '2D continuation'
    else:
        break_up, break_down = '2U', '2D'

    return {
        "available": valid,
        "reason": None if valid else 'invalid latest OHLC',
        "basis_candle": last_candle,
        "basis_combo": last_combo,
        "is_inside_setup": last_candle == '1',
        "trigger_high": th,
        "trigger_low": tl,
        "mid_trigger": mid,
        "break_up": break_up,
        "break_down": break_down,
    }


def _bar_record(idx, row, candle: str, combo: str,
                trigger_high=None, trigger_low=None) -> Dict[str, Any]:
    flags = _derive_strat_flags(combo, candle)
    prices = pd.to_numeric(row[['Open', 'High', 'Low', 'Close']], errors='coerce')
    prices = {name.lower(): float(value) if pd.notna(value) and np.isfinite(value) else None
              for name, value in prices.items()}
    try:
        period = str(idx.date()) if hasattr(idx, 'date') else str(idx)
    except Exception:
        period = str(idx)
    return {
        "period": period,
        **prices,
        "candle": candle,
        "combo": combo,
        # Strat trigger lines = the PRIOR bar's high/low.
        "trigger_high": float(trigger_high) if pd.notna(trigger_high) else None,
        "trigger_low": float(trigger_low) if pd.notna(trigger_low) else None,
        **flags,
    }


def compute_strat_history(
    ticker: str,
    df: Optional[pd.DataFrame] = None,
    timeframes: Optional[list[str]] = None,
    lookback: int = 20,
    strat_config: Optional[StratConfig] = None,
    *, as_of=None, price_basis=None, rule_version=None, input_identity=None,
) -> Dict[str, Any]:
    """Historical Strat classification per timeframe + the upcoming setup.

    Resamples daily bars up to each requested timeframe (daily/weekly/monthly/
    quarterly), retaining partial-period coverage and invalid positions. Explicit
    contracts require an aware observation instant, declared coherent basis and
    source identity. Source-backed admission remains blocked by the absent merged
    DATA basis helper. Unannotated supplied frames retain descriptive, unverified
    compatibility only; their labels cannot support a persisted comparison.
    """
    from lib.data_loader import DataLoader, _session_labels

    # No contract at all keeps the existing descriptive tooling path (report and
    # backtest CLIs), explicitly unverified and never comparable. Any contract
    # argument opts into full admission, which refuses before a loader exists.
    compatibility = (as_of is None and price_basis is None
                     and rule_version is None and input_identity is None)
    clock, identity = _history_contract(as_of, price_basis, rule_version,
                                        input_identity, supplied_frame=df,
                                        compatibility=compatibility)

    timeframes = timeframes or STRAT_HISTORY_TIMEFRAMES
    loader = DataLoader()
    if df is None:
        # Reached only without a contract: _history_contract refuses a
        # contracted source load until the merged DATA basis helper exists.
        df = loader.load_daily(ticker)
    df = df.copy() if df is not None else pd.DataFrame()
    if not compatibility and len(df):
        df.index = _session_labels(df.index)
        if df.index.has_duplicates or not df.index.is_monotonic_increasing:
            raise ValueError('history requires ordered unique session labels')
        # A daily label is a session identity, never a publication instant.
        schedule = session_schedule(df.index.min().date(), df.index.max().date())
        closes = schedule['market_close'].reindex(df.index)
        df = df.loc[(closes.notna() & (closes <= clock)).to_numpy()].copy()
        df.attrs.update(source_resolution='1d', timestamp_semantics='session_label',
                        session_policy='NYSE_regular')
        import hashlib, json
        payload = {'columns':list(df.columns), 'index':[str(x) for x in df.index],
                   'rows':finite_snapshot(df.astype(object).where(df.notna(),None).values.tolist()),
                   'attributes':finite_snapshot(df.attrs)}
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',', ':'),
                                          allow_nan=False,default=_history_timestamp_json).encode()).hexdigest()
        claim = identity['input_sha256']
        if claim is not None and claim != digest:
            raise ValueError('input content hash differs from admitted frame')
        identity.update(input_sha256=digest,code_sha256=_history_code_sha256(),
                        configuration={'aggregation_policy':'observed_v2',
                                       'timeframes':timeframes})
    metadata = {'rule_version':rule_version or 'strat-state-v2',
                'observation_ts':None if compatibility else clock.isoformat(),
                'identity':identity, 'qualification':'descriptive_unverified',
                'source_acquisition_status':'unknown', 'current_action_available':False,
                'comparison_available':not compatibility,
                'data_as_of':(schedule['market_close'].reindex(df.index).iloc[-1].tz_convert(ET_NAME).isoformat()
                              if not compatibility and len(df) else None),
                'aggregation_policy':'legacy_v1' if compatibility else 'observed_v2'}
    if df is None or df.empty or len(df) < 2:
        return {**metadata, "available": False, "ticker": ticker.upper(),
                "reason": f"insufficient daily bars for {ticker}"}

    strat = StratClassifier(strat_config=strat_config,rule_version=metadata['rule_version'])
    out: Dict[str, Any] = {**metadata, "available": True, "ticker": ticker.upper(), "timeframes": {}}

    for tf in timeframes:
        tf_df = (df if tf == '1d' else loader.aggregate_to_timeframe(df, tf)) if compatibility else loader.aggregate_to_timeframe(
            df,tf,observation_ts=clock,aggregation_policy='observed_v2')
        # Retain invalid observation positions: dropping one would invent adjacency.
        if tf_df.empty or len(tf_df) < 2:
            out["timeframes"][tf] = {"available": False,
                                     "reason": f"insufficient {tf} bars"}
            continue
        labels = strat.classify_series(tf_df)
        combos = strat.detect_combos(tf_df, labels)
        gaps = _gap_before(tf_df)
        records = [
            _bar_record(idx, tf_df.loc[idx], str(labels.loc[idx]),
                        str(combos['strat_combo'].loc[idx]),
                        None if gaps.loc[idx] else combos['trigger_high'].loc[idx],
                        None if gaps.loc[idx] else combos['trigger_low'].loc[idx])
            for idx in tf_df.index
        ]
        valid=validate_ohlc_rows(tf_df)
        for position,(idx,record) in enumerate(zip(tf_df.index,records)):
            reasons=[]
            if not valid.iloc[position]:
                reasons.append('invalid_ohlc')
            if position and not valid.iloc[position-1]:
                reasons.append('invalid_previous_ohlc')
            if gaps.iloc[position]:
                reasons.append('missing_previous_observation')
            if position==0:
                reasons.append('first_observation')
            record['bar_validity']={'valid':bool(valid.iloc[position]),'reasons':reasons}
            record['pattern_facts']=combos['pattern_facts'].loc[idx]
        history = records[-lookback:]
        out["timeframes"][tf] = {
            "available": True,
            "history": history,
            "current": history[-1],
            "upcoming": _upcoming_setup(tf_df, labels, combos),
            "coverage":tf_df.attrs.get('coverage'),
        }

    return out


@lru_cache(maxsize=1)
def _history_code_sha256():
    """Local source content identity of the history engine, never a Git revision."""
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for name in ('lib/strat.py', 'lib/data_loader.py', 'lib/eastern_time.py', 'lib/config.py'):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def _history_timestamp_json(value):
    """Encode supported timestamp scalars without guessing zones or stringifying objects.

    Tags keep timestamp content distinct from ordinary string columns. Existing
    JSON-native values never reach this encoder and retain their digest bytes.
    """
    from datetime import datetime, date
    timestamp_types = {pd.Timestamp: 'pandas.Timestamp', datetime: 'datetime', date: 'date'}
    kind = timestamp_types.get(type(value))
    if kind is not None:
        return {'timestamp_type':kind, 'iso8601':value.isoformat()}
    if type(value) is np.datetime64:
        if np.isnat(value):
            return None
        return {'timestamp_type':'numpy.datetime64', 'iso8601':np.datetime_as_string(value),
                'dtype':str(value.dtype)}
    raise TypeError(f'unsupported history identity value type: {type(value).__name__}')


def _history_contract(as_of, price_basis, rule_version, input_identity, *,
                      supplied_frame=None, compatibility=False):
    """Admit history before constructing a loader. No source qualification here.

    The genuine merged DATA basis helper is absent. Source-backed history thus
    refuses; coherent synthetic frames exercise the pure engine contract only.
    """
    if compatibility:
        return None, None
    clock = pd.Timestamp(eastern_now() if as_of is None else as_of)
    if pd.isna(clock) or clock.tzinfo is None:
        raise ValueError('history as_of must be an aware observation instant')
    clock = clock.tz_convert(ET_NAME)
    if rule_version not in ('strat-state-v2','legacy-pattern-v1'):
        raise ValueError('explicit supported history rule_version required')
    if price_basis not in ('synthetic_coherent','av-adjusted-daily-v1'):
        raise ValueError('unsupported or mixed history price basis')
    if (not isinstance(input_identity,dict) or
        set(input_identity)-{'source_revision','artifact_id','input_sha256'} or
        not all(isinstance(input_identity.get(k),str) and input_identity[k].strip()
                for k in ('source_revision','artifact_id'))):
        raise ValueError('explicit input identity source_revision/artifact_id required')
    claim=input_identity.get('input_sha256')
    if claim is not None and (not isinstance(claim,str) or len(claim)!=64 or
                              any(c not in '0123456789abcdef' for c in claim)):
        raise ValueError('invalid input content hash')
    if supplied_frame is None or price_basis != 'synthetic_coherent':
        raise ValueError('source price basis admission unavailable: merged DATA helper required')
    if supplied_frame.attrs.get('price_basis') != price_basis:
        raise ValueError('mixed or undeclared supplied frame price basis')
    for key,want in (('source_resolution','1d'),('timestamp_semantics','session_label'),
                     ('session_policy','NYSE_regular')):
        if supplied_frame.attrs.get(key) != want:
            raise ValueError(f'unsupported history source contract: {key}')
    return clock, {'rule_version':rule_version,'alignment_version':'legacy-candle-v1',
                   'price_basis':price_basis,'input_sha256':claim,
                   'source_revision':input_identity['source_revision'],
                   'artifact_id':input_identity['artifact_id'],
                   'configuration':None,'code_sha256':None}
