"""
Signal generation — 3-of-5 condition scoring for CALL and PUT entries,
with optional Strat bonus integration (up to +3 points for max 8-point scale).

Extracted from analyze_market_data_enhanced.py and unified with the
alert parameters from alert_config.json.
"""

import logging

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional

from lib.config import IndicatorConfig, SignalConfig

log = logging.getLogger(__name__)


def _factor_allowed(name: str, enabled_conditions: Optional[List[str]]) -> bool:
    """Return True if `name` (an internal factor identity — see the module
    docstring / CALL and PUT factor lists below) should be scored.

    `enabled_conditions is None` (the default everywhere in production —
    gcp/signal_monitor.py and the live endpoints never pass this) means
    "score everything", i.e. today's behaviour, byte-identical. When set,
    it's an exact allowlist: a factor not named in it contributes 0
    regardless of whether its underlying indicator condition is true.
    """
    return enabled_conditions is None or name in enabled_conditions


def check_call_conditions(
    row: pd.Series,
    consecutive_periods: int = 3,
    rsi_range: Tuple[float, float] = (25.0, 50.0),
    ema_proximity: float = 0.1,
    stoch_rsi_threshold: float = 30.0,
    indicator_config: IndicatorConfig = None,
    enabled_conditions: Optional[List[str]] = None,
) -> Tuple[int, List[str]]:
    """Evaluate CALL signal conditions for a single bar.

    Returns (score, list_of_conditions_met) where score is 0-5.

    `enabled_conditions`: when provided, only factors whose internal name
    appears in the list are scored — see `_factor_allowed`. CALL's factor
    names are `consecutive_down`, `rsi_oversold_zone`, `below_vwap`,
    `stoch_rsi_oversold`, `level_break_pdh`. Default `None` scores all of
    them, matching pre-existing behaviour exactly.
    """
    ind = indicator_config or IndicatorConfig()
    score = 0
    conditions = []

    # 1. Consecutive down periods (contrarian — buy after selling pressure)
    if (_factor_allowed('consecutive_down', enabled_conditions)
            and row.get('Consecutive_Down', 0) >= consecutive_periods):
        score += 1
        conditions.append('consecutive_down')

    # 2. RSI in bullish zone (oversold but not extreme)
    rsi = row.get(ind.rsi_col, 50.0)
    if (_factor_allowed('rsi_oversold_zone', enabled_conditions)
            and rsi_range[0] < rsi < rsi_range[1]):
        score += 1
        conditions.append('rsi_oversold_zone')

    # 3. Price below VWAP (contrarian — buying under fair value)
    price_vs_vwap = row.get('Price_vs_VWAP', 0.0)
    if (_factor_allowed('below_vwap', enabled_conditions)
            and price_vs_vwap < 0):
        score += 1
        conditions.append('below_vwap')

    # Phase 0.7.2: dropped `near_below_emas` (was 84.6% fire rate per
    # §3.10 strategy audit — pure free score). The EMA proximity columns
    # are still computed by lib/indicators and recorded on signal rows
    # for analysis, just not contributing to the score anymore.

    # 5. Stochastic RSI oversold
    stoch_k = row.get('StochRSI_K', 50.0)
    if (_factor_allowed('stoch_rsi_oversold', enabled_conditions)
            and stoch_k < stoch_rsi_threshold):
        score += 1
        conditions.append('stoch_rsi_oversold')

    # 6. Level break aligned with direction (Strat v2 — see methodology §6).
    # Reads Broke_Prev_Day_High from market_data_daily / calculate_historical_levels.
    if (_factor_allowed('level_break_pdh', enabled_conditions)
            and int(row.get('Broke_Prev_Day_High', 0) or 0) == 1):
        score += 1
        conditions.append('level_break_pdh')

    return score, conditions


def check_put_conditions(
    row: pd.Series,
    consecutive_periods: int = 3,
    rsi_range: Tuple[float, float] = (50.0, 75.0),
    ema_proximity: float = 0.1,
    stoch_rsi_threshold: float = 70.0,
    indicator_config: IndicatorConfig = None,
    enabled_conditions: Optional[List[str]] = None,
) -> Tuple[int, List[str]]:
    """Evaluate PUT signal conditions for a single bar.

    Returns (score, list_of_conditions_met) where score is 0-5.

    `enabled_conditions`: when provided, only factors whose internal name
    appears in the list are scored — see `_factor_allowed`. PUT's factor
    names are `consecutive_up`, `rsi_overbought_zone`, `above_vwap`,
    `stoch_rsi_overbought`, `level_break_pdl`. Default `None` scores all of
    them, matching pre-existing behaviour exactly. Note these names never
    overlap with CALL's factor names, so passing a CALL profile's
    (CALL-only) allowlist here naturally zeroes every PUT factor — see
    `lib.walk_forward.profile_to_signal_config`.
    """
    ind = indicator_config or IndicatorConfig()
    score = 0
    conditions = []

    # 1. Consecutive up periods (contrarian — sell after buying pressure)
    if (_factor_allowed('consecutive_up', enabled_conditions)
            and row.get('Consecutive_Up', 0) >= consecutive_periods):
        score += 1
        conditions.append('consecutive_up')

    # 2. RSI in bearish zone (overbought but not extreme)
    rsi = row.get(ind.rsi_col, 50.0)
    if (_factor_allowed('rsi_overbought_zone', enabled_conditions)
            and rsi_range[0] < rsi < rsi_range[1]):
        score += 1
        conditions.append('rsi_overbought_zone')

    # 3. Price above VWAP (contrarian — selling over fair value)
    price_vs_vwap = row.get('Price_vs_VWAP', 0.0)
    if (_factor_allowed('above_vwap', enabled_conditions)
            and price_vs_vwap > 0):
        score += 1
        conditions.append('above_vwap')

    # Phase 0.7.2: dropped `near_above_emas` (PUT-side mirror of the
    # CALL-side `near_below_emas` drop). Same 84.6% free-fire issue.

    # 5. Stochastic RSI overbought
    stoch_k = row.get('StochRSI_K', 50.0)
    if (_factor_allowed('stoch_rsi_overbought', enabled_conditions)
            and stoch_k > stoch_rsi_threshold):
        score += 1
        conditions.append('stoch_rsi_overbought')

    # 6. Level break aligned with direction (Strat v2 — see methodology §6).
    if (_factor_allowed('level_break_pdl', enabled_conditions)
            and int(row.get('Broke_Prev_Day_Low', 0) or 0) == 1):
        score += 1
        conditions.append('level_break_pdl')

    return score, conditions


#: Every condition name `check_call_conditions` / `check_put_conditions` can
#: record, and therefore the only names `disabled_conditions` may carry. A
#: name outside this set disables nothing while looking like it does, so it
#: is rejected rather than ignored (Codex on #1022). Kept honest by
#: tests/lib/test_signals_per_ticker_overrides.py::
#: test_the_disableable_condition_set_matches_what_the_checks_emit.
DISABLEABLE_CONDITIONS = frozenset({
    "above_vwap", "below_vwap",
    "consecutive_down", "consecutive_up",
    "level_break_pdh", "level_break_pdl",
    "rsi_overbought_zone", "rsi_oversold_zone",
    "stoch_rsi_overbought", "stoch_rsi_oversold",
})


def evaluate_signal(
    row: pd.Series,
    min_conditions: int = 3,
    consecutive_periods: int = 3,
    call_rsi_range: Tuple[float, float] = (25.0, 50.0),
    put_rsi_range: Tuple[float, float] = (50.0, 75.0),
    strat_bonus: int = 0,
    signal_config: SignalConfig = None,
    indicator_config: IndicatorConfig = None,
    ticker: Optional[str] = None,
    enabled_conditions: Optional[List[str]] = None,
) -> Optional[dict]:
    """Evaluate both CALL and PUT conditions for a single bar.

    Returns a signal dict if conditions are met, else None.
    The `strat_bonus` parameter adds 0-3 points from Strat integration.

    If `signal_config` is provided its values override the individual
    parameters for EMA proximity and StochRSI thresholds.

    `enabled_conditions` (trading-logic fix, Task 4.3 follow-up, review of
    commit 1c7a7f35): an exact allowlist of internal factor names (see
    `check_call_conditions` / `check_put_conditions` for the fixed CALL/PUT
    factor-name lists) passed straight through to both. `None` (the
    default; every production caller — gcp/signal_monitor.py, the live
    endpoints, `lib.backtest` unless a profile-restricted `SignalConfig` is
    used) scores the full 5-factor set on both sides, byte-identical to
    behaviour before this parameter existed. When set, a factor absent
    from the list contributes 0 regardless of the underlying indicator
    value, and — because CALL's and PUT's factor names never overlap — a
    CALL-only allowlist forces `put_score` to 0 and vice versa, so a
    direction with zero enabled factors can never fire.

    `ticker` (Track A G.P0.12 + G.P0.13 + G.P1.19): when provided,
    consults `lib.strategies.exit_config_overrides` for two per-ticker
    overrides:
      * `disabled_conditions` — strips matching factor names from the
        scoring set BEFORE comparing against `min_conditions`. Used
        globally to remove `above_vwap` from MR PUT (anti-signal,
        −16.1pp QQQ / −11.7pp IWM / −9.9pp SPY) and per-ticker to
        remove `stoch_rsi_overbought` + `rsi_overbought_zone` from
        IWM/QQQ MR PUT.
      * `disabled_directions` — full-direction kill switch. Set
        `["PUT"]` for QQQ until the MR PUT condition set is rebuilt
        (G.P1.19 — current QQQ MR PUT win-rate is 11.1%, the worst
        of any (ticker, direction) pair in the system).

    With `ticker=None` (legacy callers / backtests), behaviour is
    unchanged.
    """
    sig_cfg = signal_config
    ema_prox = sig_cfg.ema_proximity_threshold if sig_cfg else 0.1
    stoch_oversold = sig_cfg.stoch_rsi_oversold if sig_cfg else 30.0
    stoch_overbought = sig_cfg.stoch_rsi_overbought if sig_cfg else 70.0

    call_score, call_conds = check_call_conditions(
        row, consecutive_periods, call_rsi_range,
        ema_proximity=ema_prox, stoch_rsi_threshold=stoch_oversold,
        indicator_config=indicator_config,
        enabled_conditions=enabled_conditions,
    )
    put_score, put_conds = check_put_conditions(
        row, consecutive_periods, put_rsi_range,
        ema_proximity=ema_prox, stoch_rsi_threshold=stoch_overbought,
        indicator_config=indicator_config,
        enabled_conditions=enabled_conditions,
    )

    # Per-ticker overrides — strip disabled conditions and gate
    # disabled directions. PR #329 added these to the offline
    # MeanReversionStrategy path; this is the live-path wiring that
    # PR #329 missed (caught during 2026-05-09 validation when 5/8
    # alerts still showed above_vwap on 95/98 IWM PUTs).
    #
    # `disabled_directions` parsing was deduplicated into
    # `lib.strategies.exit_config_overrides.get_disabled_directions`
    # (extracted in PR #371 for the standalone-momentum path); this
    # function delegates to it so all fire paths (mr live + mr
    # backtest + standalone momentum) share one parser. The
    # `disabled_conditions` strip stays inline because it has to mutate
    # the local `call_conds` / `put_conds` lists + scores.
    disabled_directions: set[str] = set()
    if ticker:
        try:
            from lib.strategies.exit_config_overrides import (
                _latest_overrides,
                get_disabled_directions,
            )
            ov = _latest_overrides(ticker.upper())
            if ov:
                # NOT `or []`: that ran before any shape check, so `{}`, `0`,
                # `""` and `False` all became "nothing is disabled" and failed
                # OPEN on the operator config C-04 deliberately made fail
                # closed. Only None means nothing is disabled (Codex on #1022,
                # round 23).
                dc = ov.get("disabled_conditions")
                if isinstance(dc, str):
                    import json as _json
                    try:
                        dc = _json.loads(dc)
                    except ValueError:
                        # Audit C-04, closed the safe way round: a malformed
                        # disabled_conditions used to become "nothing is
                        # disabled", so a condition an operator switched OFF
                        # for risk was switched back on. Operator config we
                        # own is an INTERNAL failure; no signal fires for
                        # this bar until it is fixed (CLAUDE.md 3.7).
                        log.exception(
                            "%s: exit_config_overrides.disabled_conditions is not "
                            "valid JSON (%r); no mean-reversion signal fires for this "
                            "bar until the override row is fixed",
                            ticker, dc)
                        return None
                if dc is not None:
                    # A dict passes `set(...)` and yields its KEYS, so
                    # `{"above_vwap": False}` disabled the very condition it
                    # recorded as not disabled — the inverse of the operator's
                    # intent. And an unrecognised name disables nothing while
                    # looking like it does, which is how a typo becomes a
                    # silent no-op. Both fail closed, like the decode above.
                    if not isinstance(dc, (list, tuple)) or \
                            any(c not in DISABLEABLE_CONDITIONS for c in dc):
                        log.error(
                            "%s: exit_config_overrides.disabled_conditions is not a "
                            "list of known condition names (%r); no mean-reversion "
                            "signal fires for this bar until the override row is "
                            "fixed. Known: %s",
                            ticker, dc, sorted(DISABLEABLE_CONDITIONS))
                        return None
                if dc:
                    disabled_set = set(dc)
                    pre_call = len(call_conds)
                    pre_put = len(put_conds)
                    call_conds = [c for c in call_conds if c not in disabled_set]
                    put_conds = [c for c in put_conds if c not in disabled_set]
                    call_score -= (pre_call - len(call_conds))
                    put_score -= (pre_put - len(put_conds))
            disabled_directions = get_disabled_directions(ticker.upper())
        except Exception:
            # Audit C-04, closed the safe way round: the resolver failing
            # used to evaluate "with NO disabled conditions or directions
            # applied", so a side switched OFF for risk fired. A kill
            # switch that cannot be read is unknown, and the safe reading
            # of an unknown risk control is CLOSED: no mean-reversion
            # signal fires for this bar. The failure (import, DB, parse) is
            # logged here with its traceback, whichever layer raised it;
            # the bar recurs every 60 s, so a transient blip costs one
            # evaluation, not a fire on a disabled side (CLAUDE.md 3.7).
            log.exception(
                "%s: exit-override resolver failed; no mean-reversion signal "
                "fires for this bar", ticker)
            return None

    signal = None

    if (call_score >= min_conditions
            and call_score >= put_score
            and "CALL" not in disabled_directions):
        total_score = call_score + strat_bonus
        signal = {
            'direction': 'CALL',
            'base_score': call_score,
            'strat_bonus': strat_bonus,
            'total_score': total_score,
            'conditions_met': call_conds,
        }
    elif (put_score >= min_conditions
            and "PUT" not in disabled_directions):
        total_score = put_score + strat_bonus
        signal = {
            'direction': 'PUT',
            'base_score': put_score,
            'strat_bonus': strat_bonus,
            'total_score': total_score,
            'conditions_met': put_conds,
        }

    return signal


def generate_signals(
    df: pd.DataFrame,
    min_conditions: int = 3,
    consecutive_periods: int = 3,
    call_rsi_range: Tuple[float, float] = (25.0, 50.0),
    put_rsi_range: Tuple[float, float] = (50.0, 75.0),
    signal_config: SignalConfig = None,
    indicator_config: IndicatorConfig = None,
) -> pd.DataFrame:
    """Scan an indicator-enriched DataFrame for CALL/PUT signals.

    Returns a DataFrame of detected signals with columns:
    index, direction, base_score, total_score, conditions_met,
    and all indicator values at the signal bar.
    """
    ind = indicator_config or IndicatorConfig()
    signals = []

    for idx in range(consecutive_periods, len(df)):
        row = df.iloc[idx]

        # Skip bars with missing critical indicators
        if pd.isna(row.get(ind.rsi_col)) or pd.isna(row.get('Close', row.get('Last'))):
            continue
        if pd.isna(row.get('Price_vs_VWAP')) or pd.isna(row.get('StochRSI_K')):
            continue

        sig = evaluate_signal(
            row,
            min_conditions=min_conditions,
            consecutive_periods=consecutive_periods,
            call_rsi_range=call_rsi_range,
            put_rsi_range=put_rsi_range,
            signal_config=signal_config,
            indicator_config=indicator_config,
            # #702 follow-ups Task 2 item 3: was previously omitted here,
            # an inert asymmetry with lib/backtest.py:723's `_check_entry`
            # (which threads `self.signal.enabled_conditions`) -- a
            # profile-restricted SignalConfig passed through
            # generate_signals silently scored the full 5-factor set
            # instead of the profile's own allowlist.
            enabled_conditions=signal_config.enabled_conditions if signal_config else None,
        )

        if sig:
            close_col = 'Close' if 'Close' in df.columns else 'Last'
            sig['bar_index'] = idx
            sig['time'] = df.index[idx] if isinstance(df.index, pd.DatetimeIndex) else row.get('Time')
            sig['price'] = row[close_col]
            sig['rsi'] = row.get(ind.rsi_col)
            sig['stoch_rsi_k'] = row.get('StochRSI_K')
            sig['ema_fast'] = row.get(f'EMA{ind.ema_fast_period}')
            sig['ema_mid'] = row.get(f'EMA{ind.ema_mid_period}')
            sig['vwap'] = row.get('VWAP')
            sig['atr'] = row.get(ind.atr_col)
            sig['rvol'] = row.get('RVOL')
            signals.append(sig)

    return pd.DataFrame(signals) if signals else pd.DataFrame()


# Historical score metadata only. These definitions do not evaluate conditions.
# Match IDs are captured in the native producer branches that count them.
MOMENTUM_CONDITION_IDS = {
    'call': ('consecutive_up', 'rsi_bullish_zone', 'above_vwap', 'above_ema9',
             'rvol_above_recent', 'atr_expansion', 'rsi_thrust_up'),
    'put': ('consecutive_down', 'rsi_bearish_zone', 'below_vwap', 'below_ema9',
            'rvol_above_recent', 'atr_expansion', 'rsi_thrust_down'),
}
HISTORICAL_MR_CONDITION_IDS = {
    'call': ('consecutive_down', 'rsi_oversold_zone', 'below_vwap',
             'stoch_rsi_oversold', 'level_break_pdh'),
    'put': ('consecutive_up', 'rsi_overbought_zone', 'above_vwap',
            'stoch_rsi_overbought', 'level_break_pdl'),
}
_SCORE_KEYS = frozenset({
    'version', 'status', 'kind', 'base_count', 'base_max', 'matched_conditions',
    'bonuses', 'bonus_total', 'composite_strength', 'composite_max',
    'unavailable_reasons', 'provenance',
})
_SCORE_PROVENANCE_KEYS = frozenset({
    'corpus', 'strategy', 'run_kind', 'storage_source', 'producer_definition',
    'profile', 'direction', 'code_sha256', 'config_sha256', 'input_sha256',
    'generated_at', 'inserted_at',
})



def _score_input_bytes(frame):
    """Lossless deterministic scalar identity; never rounded display JSON."""
    import json
    from datetime import date, datetime, timedelta

    def scalar(value):
        if value is pd.NA:
            return ['missing', 'pd.NA']
        if value is pd.NaT:
            return ['missing', 'NaT']
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float):
            return ['float', value.hex()]
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return ['datetime', type(value).__name__, value.isoformat()]
        if isinstance(value, (pd.Timedelta, timedelta)):
            return ['timedelta', str(value)]
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, bytes):
            return ['bytes', value.hex()]
        if isinstance(value, (tuple, list)):
            return [type(value).__name__, [scalar(item) for item in value]]
        raise TypeError('unsupported native score input scalar')

    payload = {
        'columns': [scalar(value) for value in frame.columns],
        'column_names': [scalar(value) for value in frame.columns.names],
        'dtypes': [str(dtype) for dtype in frame.dtypes],
        'index': [scalar(value) for value in frame.index],
        'index_names': [scalar(value) for value in frame.index.names],
        'index_dtype': str(frame.index.dtype),
        'data': [[scalar(value) for value in row] for row in frame.itertuples(index=False, name=None)],
    }
    return json.dumps(payload, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()

def score_execution_context(*, producer_definition, strategy, direction=None,
                            source_path, config, frame):
    """Record local generation identity, never original market availability.

    Reads only the explicitly supplied local source and in-memory frame. No git,
    subprocess, database, credential, provider or environment discovery.
    """
    import hashlib
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    return {
        'corpus': 'historical_signals', 'strategy': strategy,
        'run_kind': None, 'storage_source': None,
        'producer_definition': producer_definition, 'profile': 'historical-default',
        'direction': direction,
        # Bind both native wrapper and shared descriptor, without git or an
        # absolute executor path. Enriched inputs are hashed separately below.
        'code_sha256': hashlib.sha256(json.dumps({
            Path(path).name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in {str(Path(source_path).resolve()), str(Path(__file__).resolve())}
        }, sort_keys=True).encode()).hexdigest(),
        'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True,
            allow_nan=False).encode()).hexdigest(),
        'input_sha256': hashlib.sha256(_score_input_bytes(frame)).hexdigest(),
        'generated_at': datetime.now(timezone.utc).isoformat(), 'inserted_at': None,
    }


def _score_integer(value):
    import numbers
    import math
    return (not isinstance(value, (bool, np.bool_))
            and isinstance(value, numbers.Real) and math.isfinite(value)
            and value == int(value))


def _validate_score_explanation(value, score=None, strategy=None, direction=None):
    """Refuse malformed/unknown data; no inferred denominator or truncation."""
    import json
    import re
    from datetime import datetime

    if not isinstance(value, dict) or set(value) != _SCORE_KEYS:
        raise ValueError('score_contract_fields')
    if len(json.dumps(value, allow_nan=False, separators=(',', ':')).encode()) > 2048:
        raise ValueError('score_contract_oversize')
    if (value['version'] != 'historical-score-v1' or value['status'] != 'recorded'
            or value['unavailable_reasons'] != []):
        raise ValueError('score_contract_version_or_status')
    p = value['provenance']
    if not isinstance(p, dict) or set(p) != _SCORE_PROVENANCE_KEYS:
        raise ValueError('score_contract_provenance')
    definitions = {
        'historical-momentum-v1': ('momentum', MOMENTUM_CONDITION_IDS, 7, 'condition_count'),
        'historical-mr-v1': ('mean_reversion', HISTORICAL_MR_CONDITION_IDS, 5, 'base_plus_bonus'),
    }
    if p['producer_definition'] not in definitions:
        raise ValueError('score_contract_unknown_producer')
    native_strategy, ids, maximum, kind = definitions[p['producer_definition']]
    if (p['corpus'] != 'historical_signals' or p['strategy'] != native_strategy
            or (strategy is not None and strategy != native_strategy)
            or (direction is not None and direction != p['direction'])
            or p['profile'] != 'historical-default' or p['direction'] not in ids
            or value['kind'] != kind):
        raise ValueError('score_contract_profile_mismatch')
    for k in ('code_sha256', 'config_sha256', 'input_sha256'):
        if not isinstance(p[k], str) or not re.fullmatch('[0-9a-f]{64}', p[k]):
            raise ValueError('score_contract_identity_missing')
    if not isinstance(p['generated_at'], str) or datetime.fromisoformat(p['generated_at']).tzinfo is None:
        raise ValueError('score_contract_generation_clock')
    if p['run_kind'] not in (None, 'live', 'replay', 'backfill'):
        raise ValueError('score_contract_run_kind')
    if p['storage_source'] not in (None, 'cloud_sql', 'gcs_parquet'):
        raise ValueError('score_contract_storage_source')
    if p['inserted_at'] is not None:
        if not isinstance(p['inserted_at'], str) or datetime.fromisoformat(p['inserted_at']).tzinfo is None:
            raise ValueError('score_contract_insert_clock')
    matched = value['matched_conditions']
    if (not isinstance(matched, list) or any(not isinstance(x, str) for x in matched)
            or len(set(matched)) != len(matched) or not set(matched).issubset(ids[p['direction']])):
        raise ValueError('score_contract_conditions')
    for k in ('base_count', 'base_max', 'bonus_total', 'composite_strength'):
        if not _score_integer(value[k]):
            raise ValueError('score_contract_noninteger')
    if value['base_max'] != maximum or value['base_count'] != len(matched):
        raise ValueError('score_contract_base_mismatch')
    # Only these historical profiles have an established bonus policy: none.
    if (value['bonuses'] != [] or value['bonus_total'] != 0
            or value['composite_max'] != maximum
            or value['composite_strength'] != value['base_count']):
        raise ValueError('score_contract_total_mismatch')
    if score is not None and (not _score_integer(score) or score != value['composite_strength']):
        raise ValueError('score_contract_stored_total_mismatch')
    return value


def build_score_explanation(*, base_count, matched_conditions, provenance):
    """Describe the actual no-bonus historical producer; never recalculate it."""
    definition = provenance['producer_definition']
    maximum = {'historical-momentum-v1': 7, 'historical-mr-v1': 5}.get(definition)
    result = {
        'version': 'historical-score-v1', 'status': 'recorded',
        'kind': 'condition_count' if definition == 'historical-momentum-v1' else 'base_plus_bonus',
        'base_count': base_count, 'base_max': maximum,
        'matched_conditions': list(matched_conditions), 'bonuses': [], 'bonus_total': 0,
        'composite_strength': base_count, 'composite_max': maximum,
        'unavailable_reasons': [], 'provenance': dict(provenance),
    }
    _validate_score_explanation(result)
    return result


def read_score_explanation(value, *, score, strategy=None, direction=None, run_kind=None,
                           storage_source, inserted_at=None):
    """Allowlisted API projection; missing/invalid evidence preserves raw score.

    Current strategy or raw condition strings cannot reconstruct legacy maxima.
    Storage fields describe this read, not original source publication or receipt.
    """
    from copy import deepcopy
    import json

    reason = 'legacy_score_contract_missing'
    missing = value is None or (isinstance(value, (float, np.floating)) and np.isnan(value))
    if not missing:
        try:
            if not isinstance(value, str):
                # Arrow/pandas returns nested list columns as NumPy arrays.
                # Normalize only their JSON representation, never score math.
                def numpy_json(obj):
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                    if isinstance(obj, np.generic):
                        return obj.item()
                    raise TypeError('unsupported score contract value')
                value = json.dumps(value, default=numpy_json, allow_nan=False,
                                   separators=(',', ':'))
            if len(value.encode()) > 2048:
                raise ValueError('score_contract_oversize')
            value = json.loads(value)
            if not _score_integer(score):
                raise ValueError('score_contract_stored_total_missing')
            _validate_score_explanation(value, score=score, strategy=strategy, direction=direction)
            result = deepcopy(value)
            p = result['provenance']
            if p['run_kind'] is not None and run_kind is not None and p['run_kind'] != run_kind:
                raise ValueError('score_contract_run_kind_mismatch')
            p.update(run_kind=run_kind, storage_source=storage_source, inserted_at=inserted_at)
            _validate_score_explanation(result, score=score, strategy=strategy, direction=direction)
            return result
        except (ValueError, TypeError, KeyError, OverflowError):
            reason = 'score_contract_invalid'
    return {
        'version': 'historical-score-v1',
        'status': 'legacy_unavailable' if missing else 'invalid_record', 'kind': 'unknown',
        'base_count': None, 'base_max': None, 'matched_conditions': None,
        'bonuses': None, 'bonus_total': None, 'composite_strength': None, 'composite_max': None,
        'unavailable_reasons': [reason],
        'provenance': {
            'corpus': 'historical_signals', 'strategy': strategy, 'run_kind': run_kind,
            'storage_source': storage_source, 'producer_definition': None,
            'profile': None, 'direction': None, 'code_sha256': None, 'config_sha256': None,
            'input_sha256': None, 'generated_at': None, 'inserted_at': inserted_at,
        },
    }
