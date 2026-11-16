"""FEAT-PLAYBOOK-001 B4 and B5: what the overview model is sent, and the check on what it says.

The tests read the pure functions; no model, network or database is called.
"""
import re

import pytest

from gcp import brief_explanations as be
from lib.config import StratConfig
from lib.strat import StratClassifier
from tests.gcp.test_strat_snapshot_parity import _brief, _daily, no_network  # noqa: F401


def _iwm(**over):
    """IWM as the 2026-11-16 brief stored it (spec Problem 2)."""
    d = {'price': 276.30, 'rsi': 44.0, 'ftfc_score': -0.30 / 0.40, 'ftfc_direction': 'bearish',
         'ftfc_labels': {'1d': '2D', '1w': '1', '1mo': '2U'}, 'macd_cross': 'Bullish'}
    d.update(over)
    return d


def _line(text, ticker):
    return next(line for line in text.split('\n') if line.startswith(f'{ticker}:'))


def test_user_text_holds_each_candle_with_its_meaning():
    line = _line(be.overview_user_text({'IWM': _iwm()}), 'IWM')
    assert 'daily 2D (down)' in line
    assert 'weekly 1 (inside and neutral)' in line
    assert 'monthly 2U (up)' in line
    assert 'MACD cross Bullish' in line
    assert 'TF bias -0.75 (bearish)' in line


def test_default_weights_are_read_not_typed(monkeypatch):
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'daily 0.30' in prompt
    assert 'weekly 0.10' in prompt
    assert 'monthly none' in prompt
    # The number is not in the prompt's source: change the weight, the text follows.
    monkeypatch.setitem(StratClassifier.DEFAULT_WEIGHTS, '1d', 0.25)
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'daily 0.25' in prompt
    assert 'daily 0.30' not in prompt


def test_configured_monthly_weight_is_named():
    weights = StratClassifier(strat_config=StratConfig(
        ftfc_weights={'1d': 0.30, '1w': 0.10, '1mo': 0.20})).ftfc_weights
    prompt = be.overview_system_prompt(weights)
    assert 'monthly 0.20' in prompt
    assert 'monthly none' not in prompt


def test_prompt_says_inside_and_outside_add_nothing():
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'an inside (1) or outside (3) bar adds nothing to the score' in prompt
    assert "The score's sign is not a statement about any one timeframe" in prompt
    assert 'a weighted vote of daily and weekly candle types' not in prompt


def test_missing_labels_are_unavailable():
    d = _iwm()
    del d['ftfc_labels']
    line = _line(be.overview_user_text({'IWM': d}), 'IWM')
    assert 'candles unavailable' in line
    for label in ('2U', '2D', 'inside', 'outside'):
        assert label not in line
    line = _line(be.overview_user_text({'IWM': _iwm(ftfc_labels={'1d': '2D'})}), 'IWM')
    assert 'daily 2D (down)' in line
    assert 'weekly unavailable' in line
    assert 'monthly unavailable' in line


def test_weights_unknown_is_said():
    prompt = be.overview_system_prompt(None)
    assert 'weights unavailable' in prompt
    # No weight is printed: the only digits left are candle names (2U, 2D, 1, 3).
    assert not re.search(r'\d\.\d', prompt)
    assert 'none' not in prompt


def test_user_text_is_none_when_no_ticker_has_data():
    assert be.overview_user_text({'IWM': {'status': 'NO DATA'}}) is None
    assert be.overview_user_text({}) is None


def test_weights_property_is_a_copy():
    classifier = StratClassifier()
    weights = classifier.ftfc_weights
    weights['1d'] = 9.0
    assert classifier.ftfc_weights['1d'] == StratClassifier.DEFAULT_WEIGHTS['1d']


def test_explain_overview_sends_the_prompt_built_from_the_weights(monkeypatch):
    import asyncio
    seen = []

    async def fake_call(system, user):
        seen.append((system, user))
        return 'Volume was light into the close.'
    monkeypatch.setattr(be, '_call', fake_call)
    weights = {'1d': 0.30, '1w': 0.10, '1mo': 0.20}
    asyncio.run(be.explain_overview_setup({'IWM': _iwm()}, weights))
    system, user = seen[0]
    assert system == be.overview_system_prompt(weights)
    assert be.overview_user_text({'IWM': _iwm()}) in user


def test_brief_carries_the_weights(monkeypatch, no_network):  # noqa: F811
    pb, cfg = _brief(monkeypatch, _daily())
    cfg.strat.ftfc_weights = {'1d': 0.30, '1w': 0.10, '1mo': 0.20}
    brief = pb.generate_premarket_brief(cfg=cfg)
    assert brief['ftfc_weights'] == StratClassifier(strat_config=cfg.strat).ftfc_weights
    assert brief['ftfc_weights'] == {'1d': 0.30, '1w': 0.10, '1mo': 0.20}
