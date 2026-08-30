"""Emergency exposure ceiling (#816).

The ceiling is a safety invariant, not a tuned policy, so the property that
matters most is the FIRST test: with stock config it must not be able to block
anything, because the thresholds equal the bound `max_daily_trades` already
implies. A ceiling that quietly starts censoring fires would be worse than the
accidental bound it replaces.

The rest prove each of the three bounds actually bites once crossed, and that
a malformed position size errs toward blocking rather than toward looking
smaller than it is.
"""
import math

import pytest

from lib.config import RiskConfig
from gcp.signal_monitor import SignalMonitor


def _monitor(**risk_overrides):
    m = SignalMonitor()
    m.webhook_url = ""
    for k, v in risk_overrides.items():
        setattr(m.risk, k, v)
    return m


def _pos(size=1.0):
    return {'entry_price': 100.0, 'direction': 'CALL', 'size': size}


# --------------------------------------------------------------------------
# 1. The defaults must be a no-op.
# --------------------------------------------------------------------------

def test_defaults_equal_the_bound_max_daily_trades_already_implies():
    r = RiskConfig()
    assert r.emergency_max_concurrent_positions == r.max_daily_trades
    assert r.emergency_max_gross_exposure == pytest.approx(
        r.max_daily_trades * max(r.position_sizing.values()))


def test_defaults_cannot_block_any_reachable_state():
    """Walk every state reachable under the daily cap; none may block."""
    m = _monitor()
    cap = m.risk.max_daily_trades
    max_size = max(m.risk.position_sizing.values())
    for n in range(cap):           # 0..cap-1 open, i.e. opening the n+1'th
        m.active_positions = {'SPY': [_pos(max_size) for _ in range(n)]}
        blocked, why, _ = m._emergency_ceiling_block('SPY')
        assert not blocked, f"default ceiling blocked at {n} positions: {why}"


# --------------------------------------------------------------------------
# 2. Each bound bites once crossed.
# --------------------------------------------------------------------------

def test_count_bound_blocks():
    m = _monitor(emergency_max_concurrent_positions=2,
                 emergency_max_gross_exposure=99.0,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(0.25), _pos(0.25)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert blocked and 'concurrent 2+1 > 2' in why and st['count'] == 2


def test_gross_bound_blocks_even_when_count_is_low():
    """Two large positions can breach gross while the count bound is fine."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=1.5,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(1.0), _pos(0.75)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert blocked and 'gross 1.75' in why and st['gross'] == pytest.approx(1.75)


def test_portfolio_bound_blocks_when_no_single_ticker_would():
    """The aggregate bound is the only one that looks across tickers."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=99.0,
                 emergency_max_portfolio_gross=2.0)
    m.active_positions = {'SPY': [_pos(1.0)], 'QQQ': [_pos(1.0)],
                          'IWM': [_pos(0.5)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert blocked and 'portfolio_gross 2.50' in why
    assert st['gross'] == pytest.approx(1.0)      # this ticker alone is fine
    assert st['portfolio_gross'] == pytest.approx(2.5)


# --------------------------------------------------------------------------
# 3. Bad data must not make exposure look smaller (Rule 3.7).
# --------------------------------------------------------------------------

def test_unusable_size_counts_as_max_not_zero():
    m = _monitor()
    m.active_positions = {'SPY': [_pos('not-a-number'), _pos(None)]}
    st = m._exposure_state('SPY')
    assert st['gross'] == pytest.approx(2.0), (
        "a malformed size must count at maximum, never silently as 0")


def test_missing_size_key_defaults_to_one():
    m = _monitor()
    m.active_positions = {'SPY': [{'entry_price': 100.0, 'direction': 'CALL'}]}
    assert m._exposure_state('SPY')['gross'] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# 4. Config must fail loud on a ceiling that would block everything.
# --------------------------------------------------------------------------

@pytest.mark.parametrize('field', [
    'emergency_max_concurrent_positions',
    'emergency_max_gross_exposure',
    'emergency_max_portfolio_gross',
])
@pytest.mark.parametrize('bad', [0, -1])
def test_non_positive_ceiling_is_rejected(tmp_path, field, bad):
    """A ceiling of 0 blocks every fire. That must fail loud, not look like
    a dead strategy."""
    import json
    from lib.config import load_config
    cfg_file = tmp_path / 'alert_config.json'
    cfg_file.write_text(json.dumps({'risk_parameters': {field: bad}}))
    with pytest.raises(ValueError, match=field):
        load_config(str(cfg_file))


def test_valid_override_is_applied(tmp_path):
    import json
    from lib.config import load_config
    cfg_file = tmp_path / 'alert_config.json'
    cfg_file.write_text(json.dumps({'risk_parameters': {
        'emergency_max_concurrent_positions': 3,
        'emergency_max_gross_exposure': 2.5,
    }}))
    app = load_config(str(cfg_file))
    assert app.risk.emergency_max_concurrent_positions == 3
    assert app.risk.emergency_max_gross_exposure == pytest.approx(2.5)


# --------------------------------------------------------------------------
# 5. Codex review of PR #933 — three defects, each reproduced before fixing.
# --------------------------------------------------------------------------

def test_nan_size_does_not_disable_the_gross_ceilings():
    """`float('nan')` parses fine, poisons the accumulator, and because every
    comparison against NaN is False it SILENTLY DISABLES both gross bounds
    rather than tripping them. Reproduced pre-fix: ceiling 0.5 did not block.
    """
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=0.5,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(float('nan'))]}
    st = m._exposure_state('SPY')
    assert math.isfinite(st['gross']), "a NaN size must not reach the accumulator"
    blocked, _why, _ = m._emergency_ceiling_block('SPY')
    assert blocked, "NaN size must trip the ceiling, never disable it"


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -5.0])
def test_negative_or_non_finite_size_counts_at_maximum(bad):
    """Zero is deliberately NOT in this list — see the zero-size tests below.
    Only values that cannot represent real exposure err toward blocking."""
    m = _monitor()
    m.active_positions = {'SPY': [_pos(bad)]}
    assert m._exposure_state('SPY')['gross'] == pytest.approx(
        m.max_position_size())


def test_negative_size_cannot_shrink_reported_exposure():
    """Pre-fix a -5.0 alongside a 1.0 reported gross = -4.0."""
    m = _monitor()
    m.active_positions = {'SPY': [_pos(1.0), _pos(-5.0)]}
    assert m._exposure_state('SPY')['gross'] == pytest.approx(2.0)


def test_pending_position_counts_toward_the_gross_ceiling():
    """The ceiling must bound the state the fire PRODUCES. Pre-fix, gross 1.0
    against a 1.5 ceiling admitted another 1.0 and landed at 2.0."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=1.5,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(1.0)]}
    blocked, why, _ = m._emergency_ceiling_block('SPY')
    assert blocked and '1.00+1.00 > 1.50' in why


def test_pending_position_counts_toward_the_portfolio_ceiling():
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=99.0,
                 emergency_max_portfolio_gross=2.0)
    m.active_positions = {'SPY': [_pos(0.5)], 'QQQ': [_pos(0.75)]}
    blocked, why, _ = m._emergency_ceiling_block('SPY')
    assert blocked and 'portfolio_gross 1.25+1.00 > 2.00' in why


def test_fractional_count_ceiling_is_rejected_not_truncated(tmp_path):
    """int(0.5) == 0 would block every fire — the dead-strategy state the
    validation exists to prevent. Pre-fix 0.5 was accepted and became 0."""
    import json
    from lib.config import load_config
    f = tmp_path / 'alert_config.json'
    f.write_text(json.dumps({'risk_parameters': {
        'emergency_max_concurrent_positions': 0.5}}))
    with pytest.raises(ValueError, match='whole number'):
        load_config(str(f))


def test_non_finite_ceiling_is_rejected(tmp_path):
    from lib.config import load_config
    f = tmp_path / 'alert_config.json'
    f.write_text('{"risk_parameters": {"emergency_max_gross_exposure": 1e999}}')
    with pytest.raises(ValueError, match='finite'):
        load_config(str(f))


# --------------------------------------------------------------------------
# 3. The conservative stand-in must itself be trustworthy.
#
#    `max_position_size()` is what `_usable_size` substitutes for a bad size
#    AND the pending size in `_emergency_ceiling_block`. If it can return NaN
#    the fix above is undone one layer up: the NaN flows back into both gross
#    accumulators and disables the very ceilings it defends.
# --------------------------------------------------------------------------

def _sizing(**kw):
    base = {'weak': 0.25, 'medium': 0.50, 'strong': 0.75, 'perfect': 1.00}
    base.update(kw)
    return base


def test_nan_in_the_sizing_config_does_not_poison_the_fallback():
    """`json.loads` accepts a bare NaN, and 'weak' is the first entry, so
    `max()` sees NaN first and returns it. Pre-fix that made the stand-in NaN
    and both gross ceilings stopped tripping."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=0.5,
                 emergency_max_portfolio_gross=0.5)
    m.risk.position_sizing = _sizing(weak=float('nan'))

    assert math.isfinite(m.max_position_size())
    assert m.max_position_size() == pytest.approx(1.00)

    m.active_positions = {'SPY': [_pos(float('nan'))]}
    st = m._exposure_state('SPY')
    assert math.isfinite(st['gross']), "the fallback re-poisoned the accumulator"
    blocked, _why, _ = m._emergency_ceiling_block('SPY')
    assert blocked, "ceiling silently disabled by the sizing config"


@pytest.mark.parametrize('position', ['weak', 'perfect'])
def test_bad_entry_is_discarded_wherever_it_sits(position):
    """`max()` is order-dependent around NaN — it returns NaN only when NaN is
    seen first. Filtering must happen BEFORE the maximum is taken, or this
    passes for one position and fails for the other."""
    m = _monitor()
    m.risk.position_sizing = _sizing(**{position: float('nan')})
    assert math.isfinite(m.max_position_size())


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1.0, 'x', None])
def test_a_single_bad_entry_does_not_discard_the_good_ones(bad):
    m = _monitor()
    m.risk.position_sizing = _sizing(weak=bad)
    assert m.max_position_size() == pytest.approx(1.00)


def test_zero_is_legal_in_the_sizing_config_and_simply_is_not_the_maximum():
    """A zero bucket means 'do not size this signal', not a malformed config."""
    m = _monitor()
    m.risk.position_sizing = _sizing(weak=0.0, perfect=0.75)
    assert m.max_position_size() == pytest.approx(0.75)


@pytest.mark.parametrize('unusable', [
    {'weak': float('nan')},
    {'weak': 0.0},
    {},
    None,
])
def test_no_usable_entry_falls_back_to_the_named_constant(unusable):
    from gcp.signal_monitor import _FULL_POSITION_FRACTION
    m = _monitor()
    m.risk.position_sizing = unusable
    assert m.max_position_size() == pytest.approx(_FULL_POSITION_FRACTION)
    assert math.isfinite(_FULL_POSITION_FRACTION) and _FULL_POSITION_FRACTION > 0


@pytest.mark.parametrize('not_a_mapping', [[0.25, 1.0], 'x', 1.0])
def test_a_non_mapping_sizing_config_does_not_raise_out_of_the_helper(
        not_a_mapping):
    """A TypeError escaping a safety helper would take down evaluate_ticker.
    The pre-hardening version caught this; the hardened one must too."""
    from gcp.signal_monitor import _FULL_POSITION_FRACTION
    m = _monitor()
    m.risk.position_sizing = not_a_mapping
    assert m.max_position_size() == pytest.approx(_FULL_POSITION_FRACTION)


# --------------------------------------------------------------------------
# 4. A legal zero size must survive the accumulator.
#
#    `max_position_size` treats a zero bucket as legal ("don't size this
#    signal") and skips it as a candidate. `_usable_size` used to treat the
#    resulting zero-size POSITION as malformed and substitute the maximum —
#    the same value read as legal in one place and malformed in the other.
# --------------------------------------------------------------------------

def test_a_zero_sized_position_consumes_no_gross_capacity():
    """Pre-fix a size-0.0 position reported gross 1.0: a full unit of phantom
    capacity charged against a position carrying no exposure."""
    m = _monitor()
    m.active_positions = {'SPY': [_pos(0.0)]}
    assert m._exposure_state('SPY')['gross'] == pytest.approx(0.0)
    assert m._exposure_state('SPY')['portfolio_gross'] == pytest.approx(0.0)


def test_a_zero_sized_position_still_counts_toward_the_count_bound():
    """Zero exposure is still an open position. Only the gross bounds ignore
    it — otherwise a zero bucket would evade the ceiling entirely."""
    m = _monitor(emergency_max_concurrent_positions=1,
                 emergency_max_gross_exposure=99.0,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(0.0)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert st['count'] == 1
    assert blocked and 'concurrent 1+1 > 1' in why


def test_a_zero_bucket_does_not_spuriously_block_a_later_alert():
    """The end-to-end chain Codex described: a legal zero bucket flows through
    get_position_size into the stored position size, and pre-fix each such
    position charged a full 1.0 against the ceiling."""
    from lib.config import get_position_size
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=2.0,
                 emergency_max_portfolio_gross=99.0)
    m.risk.position_sizing = {'weak': 0.0, 'medium': 0.50,
                              'strong': 0.75, 'perfect': 1.00}
    weak = get_position_size(m.risk.score_thresholds[0], m.risk)
    assert weak == pytest.approx(0.0), "precondition: the weak bucket is zero"

    m.active_positions = {'SPY': [_pos(weak), _pos(weak)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert st['gross'] == pytest.approx(0.0)
    assert not blocked, f"two zero-sized positions blocked a fire: {why}"
