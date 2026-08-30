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
import pytest

from lib.config import RiskConfig, AppConfig
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
    assert blocked and 'concurrent=2' in why and st['count'] == 2


def test_gross_bound_blocks_even_when_count_is_low():
    """Two large positions can breach gross while the count bound is fine."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=1.5,
                 emergency_max_portfolio_gross=99.0)
    m.active_positions = {'SPY': [_pos(1.0), _pos(0.75)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert blocked and 'gross=1.75' in why and st['gross'] == pytest.approx(1.75)


def test_portfolio_bound_blocks_when_no_single_ticker_would():
    """The aggregate bound is the only one that looks across tickers."""
    m = _monitor(emergency_max_concurrent_positions=99,
                 emergency_max_gross_exposure=99.0,
                 emergency_max_portfolio_gross=2.0)
    m.active_positions = {'SPY': [_pos(1.0)], 'QQQ': [_pos(1.0)],
                          'IWM': [_pos(0.5)]}
    blocked, why, st = m._emergency_ceiling_block('SPY')
    assert blocked and 'portfolio_gross=2.50' in why
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
